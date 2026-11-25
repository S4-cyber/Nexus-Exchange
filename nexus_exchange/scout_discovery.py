"""Capability-specific, bounded public-source search planning.

Local planning is not consent. One explicit selection may invoke exactly one
existing read-only adapter; no automatic batches, credentials in plans,
commercial dispatch, or changes to archive source-hold semantics.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3

from . import sam_search, ted_search, fts_search, cf_search, canada_search
from .governor import Action, decide
from .lead_store import _json, _digest, _now
from .scout import _timestamp
from .owner_profile import normalize_profile, profile_revision, ProfileStore
from .operator_capabilities import catalog, CSV_ID, JSON_ID, PROFILE_ID, RECONCILE_ID

FORMAT="nexus-capability-discovery-plan-v1"
MAX_OPTIONS=69
TTL=timedelta(minutes=5)
READY="REVIEW_FOR_READ_CONSENT"
_SERVICES={
    CSV_ID:("CSV standardization","csv sorting"),
    JSON_ID:("JSON-to-CSV conversion","json to csv"),
    PROFILE_ID:("CSV quality report","csv quality report"),
    RECONCILE_ID:("Two-file CSV reconciliation","csv reconciliation"),
}
_SOURCES={"sam":"SAM.gov","ted":"EU TED","uk_tender":"UK Find a Tender",
          "uk_contracts":"UK Contracts Finder","canada":"CanadaBuys",
          "usaspending":"USAspending (historical awards)"}
_FLAGS=("external_authority","execution_eligible","commercial_dispatch_enabled",
        "actual_opportunity_verified","requirements_verified","zero_capital_verified",
        "automatic_search_enabled","read_consent_granted")


def _permit(halted):
    decision=decide(Action.RESEARCH_LOCAL,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)


def _live(halt_check):
    if not callable(halt_check) or halt_check() is not False:
        raise PermissionError("HALTED_OR_UNKNOWN")


def load_profile(directory,*,halt_check):
    _live(halt_check)
    path=Path(directory)/"owner-profile.sqlite3"
    if not path.is_file():
        raise ValueError("Save a declared owner profile before planning searches.")
    with ProfileStore(path) as store:
        profile=store.load(halted=False)
    _live(halt_check)
    if profile is None:
        raise ValueError("Save a declared owner profile before planning searches.")
    return normalize_profile(profile)


def build_plan(profile,capability_id,*,now,halted=None):
    """Construct a deterministic plan from the implemented catalogue and profile."""
    _permit(halted)
    profile=normalize_profile(profile)
    now=_now(now)
    if type(capability_id) is not str or capability_id not in _SERVICES:
        raise ValueError("Choose an implemented service.")
    capabilities=catalog(halted=False)
    if sum(row["capability_id"]==capability_id for row in capabilities["capabilities"])!=1:
        raise ValueError("Implemented capability catalogue changed.")
    label,phrase=_SERVICES[capability_id]
    today=now.date()
    past=(today-timedelta(days=14)).isoformat()
    whole=now.replace(microsecond=0)
    options=[]

    def add(source,kind,value,start=None,end=None,ptype=None,requests=0,maximum=0,
            state=READY,detail=""):
        if state==READY and profile["hours_per_week"]==0:
            state="NO_DECLARED_AVAILABILITY"
        row=dict(source=source,source_label=_SOURCES[source],filter_kind=kind,
                 filter_value=value,window_start=start,window_end=end,
                 procurement_type=ptype,max_requests=requests,max_response_bytes=maximum,
                 key_required=source=="sam",state=state,detail=detail,
                 **dict.fromkeys(_FLAGS,False))
        options.append(dict(row,option_id=_digest(_json(row))))

    for source in profile["sources"]:
        if source=="sam":
            for ptype in ("k","o"):
                add(source,"TITLE_KEYWORD",phrase,past,today.isoformat(),ptype,
                    sam_search.MAX_REQUESTS,sam_search.MAX_BYTES,
                    detail="Public title search; k = combined synopsis/solicitation, o = solicitation. Own SAM API key required.")
        elif source=="canada":
            add(source,"LOCAL_TITLE_SUBSTRING",phrase,requests=1,maximum=canada_search.MAX_BYTES,
                detail="Download one official daily open-tender dataset; apply the title substring locally.")
        elif source in ("ted","uk_contracts"):
            if not profile["cpv"]:
                add(source,"DECLARED_CPV_PREFIX",None,state="CPV_DECLARATION_REQUIRED",
                    detail="Declare an appropriate CPV prefix in the owner profile; no classification inferred.")
                continue
            for prefix in profile["cpv"]:
                if source=="ted":
                    add(source,"DECLARED_CPV_PREFIX",prefix,past,today.isoformat(),
                        requests=ted_search.MAX_REQUESTS,maximum=ted_search.MAX_BYTES,
                        detail="Broad classification search, not a service-specific keyword query.")
                else:
                    add(source,"LOCAL_DECLARED_CPV_PREFIX",prefix,
                        (whole-timedelta(hours=6)).isoformat(),whole.isoformat(),
                        requests=1,maximum=cf_search.MAX_BYTES,
                        detail="One broad release page; CPV is local. Retain contrary events for review.")
        elif source=="uk_tender":
            add(source,"BROAD_RELEASE_WINDOW",None,(whole-timedelta(days=1)).isoformat(),
                whole.isoformat(),requests=fts_search.MAX_REQUESTS,maximum=fts_search.MAX_BYTES,
                detail="Broad public releases; retain all stages, then review capability hints in Matrix.")
        elif source=="usaspending":
            add(source,"HISTORICAL_AWARDS_ONLY",None,state="CONTRACTOR_INTELLIGENCE_ONLY",
                detail="Historical prime awards are not open opportunities. Use the separate research tool.")
    if len(options)>MAX_OPTIONS:
        raise ValueError("Discovery plan capacity exceeded.")
    payload=dict(format=FORMAT,capability_id=capability_id,service_label=label,
        catalog_sha256=capabilities["catalog_sha256"],profile_revision=profile_revision(profile),
        pathway=profile["mode"],planned_at=now.isoformat(timespec="microseconds"),
        expires_at=(now+TTL).isoformat(timespec="microseconds"),options=options,
        **dict.fromkeys(_FLAGS,False))
    return dict(payload,plan_sha256=_digest(_json(payload)))


def resolve_query(plan,option_id,profile,*,now,halted=None):
    """Rebuild the exact plan; reject edited rows, profile/catalog drift or expiry."""
    _permit(halted)
    now=_now(now)
    if (type(plan) is not dict or type(plan.get("options")) is not list
            or len(plan["options"])>MAX_OPTIONS or type(plan.get("planned_at")) is not str
            or type(option_id) is not str or not re.fullmatch("[0-9a-f]{64}",option_id)):
        raise ValueError("Exact discovery selection required.")
    planned=_timestamp(plan["planned_at"])
    if planned>now or now-planned>TTL:
        raise ValueError("Discovery plan expired or dated in the future. Refresh.")
    rebuilt=build_plan(profile,plan.get("capability_id"),now=planned,halted=False)
    try:
        matches=_json(plan)==_json(rebuilt)
    except (ValueError,TypeError,RecursionError):
        matches=False
    if not matches:
        raise ValueError("Discovery plan or owner profile changed. Refresh.")
    rows=[row for row in rebuilt["options"] if row["option_id"]==option_id]
    if len(rows)!=1 or rows[0]["state"]!=READY:
        raise ValueError("Selected search is unavailable.")
    row=rows[0]
    source=row["source"]
    value=row["filter_value"]
    from datetime import date
    if source=="sam":
        query=sam_search.Query(date.fromisoformat(row["window_start"]),
                               date.fromisoformat(row["window_end"]),value,row["procurement_type"])
    elif source=="ted":
        query=ted_search.TedQuery(value,date.fromisoformat(row["window_start"]),
                                  date.fromisoformat(row["window_end"]))
    elif source=="uk_tender":
        query=fts_search.FtsQuery(_timestamp(row["window_start"]),_timestamp(row["window_end"]))
    elif source=="uk_contracts":
        query=cf_search.CfQuery(_timestamp(row["window_start"]),_timestamp(row["window_end"]),value)
    elif source=="canada":
        query=canada_search.CanadaQuery(value)
        query.validated()
        return row,query
    else:
        raise ValueError("Unsupported discovery route.")
    query.parameters(now)
    return row,query


def execute_discovery(plan,option_id,profile,*,now,approved=None,halt_check=None,api_key=None):
    """Invoke one fixed adapter after trusted UI consent and fresh local checks."""
    _live(halt_check)
    if approved is not True:
        raise PermissionError("EXACT_PUBLIC_SEARCH_CONSENT_REQUIRED")
    row,query=resolve_query(plan,option_id,profile,now=now,halted=False)
    if row["key_required"]:
        if type(api_key) is not str or not re.fullmatch("[A-Za-z0-9_-]{8,256}",api_key):
            raise ValueError("Valid SAM public API key required.")
        if api_key in row["filter_value"]:
            raise ValueError("Search text contains credential.")
    elif api_key is not None:
        raise ValueError("Unexpected credential for keyless search.")
    _live(halt_check)
    source=row["source"]
    if source=="sam":
        result=sam_search.search(query,api_key,approved=True,halt_check=halt_check)
    elif source=="ted":
        result=ted_search.search(query,approved=True,halt_check=halt_check)
    elif source=="uk_tender":
        result=fts_search.search(query,approved=True,halt_check=halt_check)
    elif source=="uk_contracts":
        result=cf_search.search(query,approved=True,halt_check=halt_check)
    elif source=="canada":
        result=canada_search.search(query,approved=True,halt_check=halt_check)
    else:
        raise ValueError("Unsupported discovery route.")
    _live(halt_check)
    # Preserve the full provider report and contrary evidence; the existing
    # worker archives it before Matrix performs local capability review.
    return result


def option_text(plan,row):
    return "\n".join([
        "PUBLIC RESEARCH ONLY — "+plan["service_label"],
        "Source: "+row["source_label"],
        "Filter: "+row["filter_kind"]+" / "+(row["filter_value"] or "None"),
        "Type: "+(row["procurement_type"] or "Not applicable"),
        "Window: "+(row["window_start"] or "Daily dataset / not applicable")+" to "+(row["window_end"] or "not applicable"),
        "Maximum requests: "+str(row["max_requests"]),
        "Maximum response bytes per request: "+str(row["max_response_bytes"]),
        "State: "+row["state"],row["detail"],
        "Expires UTC: "+plan["expires_at"],
        "Plan: "+plan["plan_sha256"],
        "A search is not a buyer requirement, eligibility, authority or income. No automatic search."])


def open_discovery_window(parent,*,directory,halt_check,blocked_check,launch,smoke=False):
    """Show one local plan; only an explicit current row may be launched."""
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog
    from tkinter.scrolledtext import ScrolledText
    from .cockpit import install_cockpit, fit_geometry
    from .lead_store import LeadStore
    from .discovery_history import recent_hint, hint_text, review_receipt, receipt_review_text
    from .discovery_performance import analyze,empty_history,priority_label,option_performance_text,performance_text
    window=tk.Toplevel(parent)
    content=install_cockpit(window).content
    window.title("Nexus Exchange | Capability search planner")
    window.geometry(fit_geometry(window,1000,660))
    ttk.Label(content,text="SCOUT — Capability search planner",font=("Segoe UI",18)).pack(pady=6)
    ttk.Label(content,text="Choose an implemented service. Plans use only selected profile sources and declared CPV prefixes. One explicitly approved public search at a time.",wraplength=900).pack(padx=12)
    controls=ttk.Frame(content); controls.pack(fill="x",padx=12,pady=5)
    labels={label:key for key,(label,_) in _SERVICES.items()}
    service=tk.StringVar(master=window,value=next(iter(labels)))
    chooser=ttk.Combobox(controls,textvariable=service,values=list(labels),state="readonly",width=32)
    chooser.pack(side="left")
    tree=ttk.Treeview(content,columns=("source","filter","state","requests","priority"),show="headings",height=8)
    for key,title,width in (("source","Source",205),("filter","Filter / query",255),
                            ("state","Research state",220),("requests","Max requests",95),
                            ("priority","History priority",225)):
        tree.heading(key,text=title);tree.column(key,width=width,anchor="w")
    tree.pack(fill="x",padx=12,pady=6)
    output=ScrolledText(content,height=11,wrap="word",state="disabled")
    output.pack(fill="both",expand=True,padx=12,pady=6)
    plan=None
    rows={}
    search_history={"rows":[]}
    performance=None
    priorities={}

    def write(value):
        output.configure(state="normal");output.delete("1.0","end")
        output.insert("end",value);output.configure(state="disabled")

    def clear(message):
        nonlocal plan,performance
        plan=None;performance=None;rows.clear();priorities.clear()
        for item in tree.get_children():
            tree.delete(item)
        search_button.configure(state="disabled")
        write(message)

    def selected():
        selection=tree.selection()
        return rows.get(selection[0]) if selection else None

    def display(_event=None):
        row=selected()
        allowed=(plan is not None and row is not None and row["state"]==READY
                 and blocked_check() is False and halt_check() is False)
        search_button.configure(state="normal" if allowed else "disabled")
        if plan is not None and row is not None:
            write(option_text(plan,row)+"\n\n"+hint_text(recent_hint(row,search_history,now=datetime.now(timezone.utc)))
                  +"\n\n"+option_performance_text(priorities[row["option_id"]]))

    def refresh():
        nonlocal plan,search_history,performance
        clear("Planning locally...")
        try:
            profile=load_profile(directory,halt_check=halt_check)
            now=datetime.now(timezone.utc)
            plan=build_plan(profile,labels[service.get()],now=now,halted=halt_check())
            archive=Path(directory)/"scout-leads.sqlite3"
            search_history=empty_history(now)
            if archive.is_file():
                with LeadStore(archive) as store:
                    search_history=store.search_history(now=now,halted=halt_check())
            performance=analyze(profile,plan,search_history,now=now,halted=halt_check())
            original={row["option_id"]:row for row in plan["options"]}
            for priority in performance["ranked_options"]:
                key=priority["option_id"];row=original[key];rows[key]=row;priorities[key]=priority
                value=row["filter_value"] or row["filter_kind"]
                if row["procurement_type"]:
                    value+=" / "+row["procurement_type"]
                tree.insert("","end",iid=key,values=(row["source_label"],value,row["state"],row["max_requests"],priority_label(priority)))
            if rows:
                tree.selection_set(next(iter(rows)));display()
            else:
                write("No selected public sources. Update the declared owner profile.")
        except (ValueError,PermissionError,OSError,sqlite3.Error,KeyError):
            clear("Plan unavailable. Save a valid owner profile and resume offline.")

    def search_selected():
        row=selected();current=plan
        if (current is None or row is None or row["state"]!=READY
                or blocked_check() is not False or halt_check() is not False):
            clear("Search unavailable. Refresh the local plan when ready.")
            return
        if not messagebox.askyesno("Authorize one public research search",
                option_text(current,row)+"\n\n"+hint_text(recent_hint(row,search_history,now=datetime.now(timezone.utc)))
                +"\n\nRun only this bounded search?",parent=window):
            return
        key=None
        if row["key_required"]:
            key=simpledialog.askstring("SAM public API key","Enter your own key for this search only.",
                                       show="*",parent=window)
            if not key:
                return
        if current is not plan or row is not selected() or blocked_check() is not False or halt_check() is not False:
            clear("Selection or halt state changed. Refresh.")
            return
        clear("Submitting the selected read-only research task...")
        try:
            if launch(current,row["option_id"],approved=True,api_key=key) is not True:
                raise ValueError("Search was not launched.")
            write("One search requested. Results and archive updates appear in the dashboard. Refresh before another search.")
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError):
            write("Search not launched or selection changed. Refresh the plan.")

    def show_history():
        try:
            if blocked_check() is not False or halt_check() is not False:
                raise PermissionError("Local research unavailable.")
            archive=Path(directory)/"scout-leads.sqlite3"
            if not archive.is_file():
                write("No completed capability-search receipts yet.")
                return
            with LeadStore(archive) as store:
                history=store.search_history(now=datetime.now(timezone.utc),halted=halt_check())
            lines=["COMPLETED CAPABILITY SEARCHES — historical only",
                   "Showing "+str(history["returned"])+" of "+str(history["total"])+
                   "; failed and unarchived searches are not represented."]
            for number,item in enumerate(history["rows"],1):
                scope=item["scope"]
                lines.extend(["",str(number)+". "+item["completed_at"]+" | "+scope["source"]+" | "+
                              (scope["filter_value"] or scope["filter_kind"]),
                              str(item["requests"])+" requests | "+str(item["returned"])+
                              " returned | "+str(item["inserted"])+" newly archived observations"+
                              (" | truncated" if item["truncated"] else "")+
                              (" | future-dated" if item["future_dated"] else ""),
                              "Receipt: "+item["receipt_sha256"]])
            write("\n".join(lines))
        except (ValueError,PermissionError,OSError,sqlite3.Error):
            write("Search history unavailable. Review local storage and halt state.")


    def show_receipt(choose_index=None):
        try:
            if blocked_check() is not False or halt_check() is not False:
                raise PermissionError("Local research unavailable.")
            archive=Path(directory)/"scout-leads.sqlite3"
            if not archive.is_file():
                write("No completed capability-search receipts yet.")
                return
            with LeadStore(archive) as store:
                history=store.search_history(now=datetime.now(timezone.utc),halted=halt_check())
            if not history["rows"]:
                write("No completed capability-search receipts yet.")
                return
            lines=["SELECT A SEARCH RECEIPT — exact historical observations"]
            for number,item in enumerate(history["rows"],1):
                lines.append(str(number)+". "+item["completed_at"]+" | "+item["scope"]["source"]+
                             " | "+str(item["returned"])+" observations")
            write("\n".join(lines))
            selector=simpledialog.askinteger if choose_index is None else choose_index
            index=selector("Review receipt","Enter the numbered receipt from the displayed list.",
                           minvalue=1,maxvalue=len(history["rows"]),parent=window)
            if index is None:
                return
            if type(index) is not int or not 1<=index<=len(history["rows"]):
                raise ValueError("Invalid receipt selection.")
            if blocked_check() is not False or halt_check() is not False or not archive.is_file():
                raise PermissionError("Local research unavailable.")
            item=history["rows"][index-1]
            with LeadStore(archive) as store:
                report=review_receipt(store.db,item["task_id"],item["receipt_sha256"],
                                      now=datetime.now(timezone.utc),halted=halt_check())
            if blocked_check() is not False or halt_check() is not False:
                raise PermissionError("Local research unavailable.")
            write(receipt_review_text(report))
        except (ValueError,PermissionError,OSError,sqlite3.Error):
            write("Receipt review unavailable. The selection may be legacy, changed, future-dated, or inconsistent.")

    def show_performance():
        if performance is None or halt_check() is not False or blocked_check() is not False:
            write("Search performance unavailable. Refresh the local plan when idle.")
            return
        write(performance_text(performance))

    ttk.Button(controls,text="Refresh discovery plan",command=refresh).pack(side="left",padx=4)
    search_button=ttk.Button(controls,text="Search selected plan",command=search_selected,state="disabled")
    search_button.pack(side="left",padx=4)
    history_controls=ttk.Frame(content)
    history_controls.pack(fill="x",padx=12,pady=2,before=tree)
    ttk.Button(history_controls,text="Search history",command=show_history).pack(side="left",padx=4)
    ttk.Button(history_controls,text="Review receipt",command=show_receipt).pack(side="left",padx=4)
    ttk.Button(history_controls,text="Search performance",command=show_performance).pack(side="left",padx=4)
    tree.bind("<<TreeviewSelect>>",display,add="+")
    chooser.bind("<<ComboboxSelected>>",lambda _event:refresh(),add="+")
    refresh()
    if smoke:
        # Existing GUI smoke owns a saved SAM-only synthetic profile. No call
        # to the launch callback or network is made by this smoke test.
        if (plan is None or len(rows)!=2 or {r["procurement_type"] for r in rows.values()}!={"k","o"}
                or str(search_button.cget("state"))!="normal"
                or "PUBLIC RESEARCH ONLY" not in output.get("1.0","end")):
            raise RuntimeError("Capability discovery GUI lost its scoped plan")
        service.set("JSON-to-CSV conversion");refresh()
        if not rows or any(r["filter_value"]!="json to csv" for r in rows.values()):
            raise RuntimeError("Capability discovery GUI retained old service")
        show_history()
        if "COMPLETED CAPABILITY SEARCHES" not in output.get("1.0","end"):
            raise RuntimeError("Capability discovery GUI history missing")
        # Exercise the actual review controller with owned local evidence and
        # a deterministic selection in place of a blocking interactive dialog.
        show_receipt(choose_index=lambda *args,**kwargs:1)
        reviewed=output.get("1.0","end")
        if ("SCOUT — EXACT HISTORICAL SEARCH OBSERVATIONS" not in reviewed
                or "Synthetic GUI fixture" not in reviewed
                or "SAME_OBSERVATION" not in reviewed
                or "HISTORICAL_OBSERVATION_REVALIDATION_REQUIRED" not in reviewed):
            raise RuntimeError("Capability discovery GUI exact receipt review missing")
        show_receipt(choose_index=lambda *args,**kwargs:0)
        if "Receipt review unavailable" not in output.get("1.0","end"):
            raise RuntimeError("Capability discovery GUI accepted an invalid receipt selection")
        show_performance()
        if ("SCOUT SEARCH PERFORMANCE" not in output.get("1.0","end")
                or "Explore unmeasured filter" not in output.get("1.0","end")):
            raise RuntimeError("Capability discovery GUI performance missing")
    return window
