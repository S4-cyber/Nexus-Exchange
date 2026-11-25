"""One bounded engagement cycle. The desktop owns the repeating schedule."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from . import canada_search, fts_search, sam_search
from .account_providers import balances, planning_limit, renew_document
from .account_vault import AccountVault
from .event_store import EventStore
from .activity_feed import ActivityFeed, finding_row
from .engagement_files import run_files
from .lead_store import LeadStore
from .operator_capabilities import assess_lead, CSV_ID, JSON_ID, PROFILE_ID, RECONCILE_ID
from .review_ranking import RankingStore
from .scout_discovery import (build_plan, execute_discovery, load_profile, NoSavedProfile,
                              READY, SOURCE_LABELS)

BRIEF = "engagement-latest.json"
SERVICES = ((CSV_ID, "csv"), (JSON_ID, "json"), (PROFILE_ID, "data quality"), (RECONCILE_ID, "reconciliation"))


def utcnow():
    return datetime.now(timezone.utc)


def ensure_active(stopped):
    if stopped() is not False:
        raise PermissionError("Engagement halted.")


def search_default(source, term, now, stopped, key):
    kwargs = dict(approved=True, halt_check=stopped)
    if source == "uk_tender":
        return fts_search.search(fts_search.FtsQuery(now-timedelta(days=1), now), **kwargs)
    if source == "canada":
        return canada_search.search(canada_search.CanadaQuery(term), **kwargs)
    today = now.date()
    if source == "sam" and key:
        return sam_search.search(sam_search.Query(today-timedelta(days=14), today, term), key, **kwargs)
    raise ValueError("Unsupported baseline source.")


def read_bank(vault, stopped, now):
    record = vault.load("bank")
    if record is None:
        return None
    if 0 <= now.timestamp() - record.get("checked", 0) < 86400:
        return record
    ensure_active(stopped)
    # Cache both successful and unavailable readings to respect the provider's daily cadence.
    update = dict(record, available=None, as_of=None, checked=int(now.timestamp()))
    try:
        update.update(balances(record["access"]))
    finally:
        ensure_active(stopped)
        vault.save("bank", update)
    return update


def compile_brief(path, profile, bank, now, stopped):
    if profile is not None:
        effective = dict(profile, budget=format(planning_limit(profile, bank, now.timestamp()), ".2f"))
        with RankingStore(path) as store:
            ranks = store.rank_review(profile=effective, now=now, halted=False,
                                      operator_focus=True, limit=15)
        return [dict(title=r["title"], source=r["source"], url=r["source_url"],
                     review=r["review_tier"], next_step=r["operator_capability"]["review_tasks"][0])
                for r in ranks["rows"] if r["source"] in profile["sources"]]
    with LeadStore(path) as store:
        leads = store.browse(now=now, halted=False, limit=100)["leads"]
    rows = []
    for lead in leads:
        ensure_active(stopped)
        fit = assess_lead(lead, source_hold=None, halted=False)
        rows.append(dict(title=lead["title"], source=lead["source"], url=lead["source_url"],
                         review=fit["state"], next_step=fit["review_tasks"][0]))
    order = ("IMPLEMENTED_TITLE_HINT_ONLY", "NO_IMPLEMENTED_TITLE_HINT", "SOURCE_HELD")
    rows.sort(key=lambda r: order.index(r["review"]))
    return rows[:15]


def cycle(directory, stopped, progress, *, default_search=search_default, clock=utcnow):
    directory = Path(directory)
    ensure_active(stopped)
    event = EventStore(directory / "events.sqlite3")
    task = uuid4().hex
    activity = ActivityFeed(event.db)
    def stages(rows):
        activity.put(task, [(task + "/" + key, state, title, detail) for key, state, title, detail in rows], clock())
    def stage(key, state, title, detail=""):
        stages([(key, state, title, detail)])
    def journal(state):
        event.append(dict(task_id=task, target="Autonomous Scout cycle", state=state,
                          timestamp=clock().isoformat()))
    try:
        journal("queued")
        journal("running")
        try:
            profile = load_profile(directory, halt_check=stopped)
        except NoSavedProfile:
            profile = None
        sources = profile["sources"] if profile else ["uk_tender", "canada", "sam"]
        stages([(s, "Pending", SOURCE_LABELS[s], "Queued for discovery.") for s in sources if profile or s != "sam"] +
               [("brief", "Pending", "Compile review shortlist", ""),
                ("files", "Pending", "Process local work files", "")])
        vault = AccountVault(directory)
        notes, outcomes = [], []
        try:
            grant = vault.load("docusign")
            if grant and grant["expires"] <= clock().timestamp() + 120:
                ensure_active(stopped)
                if grant.get("refresh"):
                    stage("document", "Engaged", "Renew DocuSign consent")
                    progress("Renewing DocuSign consent")
                    renewed = renew_document(grant)
                    ensure_active(stopped)
                    vault.save("docusign", renewed)
                    stage("document", "Completed", "Renew DocuSign consent")
                else:
                    stage("document", "Needs attention", "DocuSign consent", "Reconnect in Accounts.")
                    notes.append("DocuSign consent expired. Reconnect in Accounts when needed.")
        except (OSError, ValueError, KeyError, TypeError):
            ensure_active(stopped)
            stage("document", "Needs attention", "DocuSign consent", "Review the connection in Accounts.")
            notes.append("DocuSign connection needs attention in Accounts.")
        bank = None
        if profile and profile["mode"] == "catalyst":
            stage("budget", "Engaged", "Check planning budget")
            progress("Checking the planning budget")
            try:
                bank = read_bank(vault, stopped, clock())
            except (OSError, ValueError, KeyError, TypeError):
                notes.append("Bank balance unavailable. Review the connection in Accounts.")
            if planning_limit(profile, bank, clock().timestamp()) == 0:
                notes.append("Using a $0 planning limit. Check Accounts and your budget in Settings.")
                stage("budget", "Needs attention", "Check planning budget", "Review Accounts and Settings.")
            else:
                stage("budget", "Completed", "Check planning budget")
        stamp = clock()
        period = int(stamp.timestamp() // 3600)
        capability, term = SERVICES[period % len(SERVICES)]
        path = directory / "scout-leads.sqlite3"
        for source in sources:
            ensure_active(stopped)
            label = SOURCE_LABELS[source]
            key = None
            if source == "sam":
                try:
                    key = (vault.load("sam") or {}).get("key")
                except (OSError, ValueError):
                    notes.append("Reconnect your SAM.gov key in Accounts.")
                if not key:
                    if profile:
                        stage(source, "Skipped", label, "Add a SAM.gov key in Accounts to enable this source.")
                        notes.append("Add a SAM.gov key in Accounts to enable this source.")
                    continue
            now = clock()
            selection = None
            if profile:
                plan = build_plan(profile, capability, now=now, halted=False)
                choices = [r for r in plan["options"] if r["source"] == source and r["state"] == READY]
                if not choices:
                    stage(source, "Skipped", label, "Current search preferences exclude this search.")
                    notes.append(label + " skipped under current search preferences.")
                    continue
                selection = choices[(period // len(SERVICES)) % len(choices)]["option_id"]
            stage(source, "Engaged", label, "Searching the public source.")
            progress("Searching " + label)
            try:
                if profile:
                    report = execute_discovery(plan, selection, profile, now=now, approved=True,
                                               halt_check=stopped, api_key=key)
                else:
                    report = default_search(source, term, now, stopped, key)
            except Exception as error:
                ensure_active(stopped)
                code = str(error) if isinstance(error, sam_search.SearchError) else ""
                detail = ("Provider rate limit reached" if "RATE_LIMIT" in code else
                          "Check source access or account credentials" if "ACCESS_DENIED" in code else
                          "Could not reach the provider" if "TRANSPORT" in code else
                          "Provider response could not be used")
                stage(source, "Needs attention", label, detail)
                outcomes.append(dict(source=source, status="Unavailable", detail=detail, found=0, saved=0))
                continue
            ensure_active(stopped)
            receipt = (dict(plan=plan, profile=profile, option_id=selection, started_at=now,
                            task_id=uuid4().hex) if profile else None)
            with LeadStore(path) as store:
                saved = store.record(report, now=clock(), halted=False, halt_check=stopped, discovery=receipt)
            activity.put(task, [finding_row(source, label, lead) for lead in report["leads"]], clock())
            stage(source, "Completed", label, f"{report['returned']} notices returned · {saved} observations saved.")
            outcomes.append(dict(source=source, status="Searched", found=report["returned"], saved=saved))
        ensure_active(stopped)
        progress("Checking source holds and compiling the review brief")
        stage("brief", "Engaged", "Compile review shortlist")
        rows = compile_brief(path, profile, bank, clock(), stopped)
        progress("Processing and checking local work files")
        ensure_active(stopped)
        stage("brief", "Completed", "Compile review shortlist", f"{len(rows)} leads shortlisted for review.")
        stage("files", "Engaged", "Process local work files")
        jobs = run_files(directory, stopped, report=stages)
        file_note = jobs.get("issue") or ("Inbox exceeds 128 entries." if jobs["full"] else
                    f"{jobs['produced']} produced · {jobs['existing']} already complete · {jobs['held']} need attention.")
        stage("files", "Needs attention" if jobs.get("issue") or jobs["held"] or jobs["full"] else "Completed",
              "Process local work files", file_note)
        if jobs.get("issue"):
            notes.append(jobs["issue"])
        if jobs["full"]:
            notes.append("Move completed files out of Scout Inbox to reduce it to 128 entries.")
        if jobs["held"]:
            notes.append("Review held inputs in Reports → Work files.")
        succeeded = sum(s["status"] == "Searched" for s in outcomes)
        status = ("No sources enabled" if not outcomes else "Sources unavailable" if not succeeded
                  else "Partial coverage" if succeeded < len(outcomes) else "Completed")
        brief = dict(format="nexus-engagement-brief-v1", finished=clock().isoformat(), status=status,
                     sources=outcomes, jobs=jobs, notes=notes, shortlist=rows, external_actions=0)
        target = directory / BRIEF
        temp = target.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(brief, ensure_ascii=True, indent=2), encoding="utf-8")
            ensure_active(stopped)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        activity.settle(task)
        journal("failed" if outcomes and not succeeded else "succeeded")
        return brief
    except Exception:
        activity.settle(task, failed=not stopped())
        journal("cancelled" if stopped() else "failed")
        raise
    finally:
        event.close()


def brief_text(brief):
    lines = [brief["status"] + "  ·  " + brief["finished"][:16].replace("T", " ") + " UTC"]
    for item in brief["sources"]:
        text = (f"{item['found']} notices, {item['saved']} observations saved"
                if item["status"] == "Searched" else item.get("detail", "unavailable this cycle"))
        lines.append(SOURCE_LABELS[item["source"]] + " — " + text)
    jobs = brief["jobs"]
    lines.append(f"Local work files: {jobs['produced']} produced, {jobs['existing']} already complete, {jobs['held']} need review.")
    lines.extend(brief["notes"])
    lines.append(f"Review shortlist from saved leads: {len(brief['shortlist'])}")
    for row in brief["shortlist"]:
        lines.extend(("", row["title"], SOURCE_LABELS[row["source"]] + " · " + row["review"].replace("_"," ").lower(),
                      row["next_step"], row["url"]))
    return "\n".join(lines)
