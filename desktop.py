"""Nexus Exchange Windows desktop review application."""
import sys
import os
import json
import sqlite3
import webbrowser
from queue import Empty, SimpleQueue
from nexus_exchange import engagement
from nexus_exchange.engagement_reports import EngagementReports
from nexus_exchange.activity_feed import ActivityFeed, finding_row, with_shortlist
from nexus_exchange.activity_panel import ActivityPanel
from nexus_exchange.engagement_files import folder as work_folder, INBOX, OUTPUTS
from nexus_exchange.accounts_panel import install as install_accounts
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from functools import partial
from uuid import uuid4
from nexus_exchange.event_store import EventStore
from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.lead_store import LeadStore, ResultChangedError, SOURCES as LEAD_FORMATS
from nexus_exchange.owner_profile import ProfileChangedError, ProfileStore, PROFILE_SOURCES, profile_revision
from nexus_exchange.checklist_store import ChecklistStore, context_for
from nexus_exchange.scenario_workspace import open_scenario_window
from nexus_exchange.operator_workspace import open_operator_window
from nexus_exchange.csv_workspace import open_csv_window
from nexus_exchange.ranking_workspace import open_ranking_window
from nexus_exchange.scout_discovery import SOURCE_LABELS, open_discovery_window, load_profile, resolve_query, execute_discovery
from nexus_exchange.evidence import fingerprint, verify_reference, EvidenceError
from nexus_exchange.opportunity_archive import OpportunityArchive
from datetime import datetime, timezone, timedelta
from nexus_exchange.pipeline import evaluate_snapshots
from nexus_exchange.local_import import evaluate_file
from nexus_exchange.scenario_import import evaluate_scenario
from nexus_exchange.trade_registry import catalog, official_url, readiness, source_tasks, KINDS
from nexus_exchange.trade_routes import ROUTES, route_assessment
from nexus_exchange.revenue_pathways import Mode, SOURCES, CHECKS, plan_lead, source_url
from nexus_exchange.sam_search import Query, search as search_sam, SearchError, notice_url
from nexus_exchange.ted_search import TedQuery, search as search_ted, notice_url as ted_notice_url
from nexus_exchange.fts_search import FtsQuery, search as search_fts, notice_url as fts_notice_url
from nexus_exchange.cf_search import CfQuery, search as search_cf, notice_url as cf_notice_url
from nexus_exchange.canada_search import CanadaQuery, search as search_canada, notice_url as canada_notice_url
from nexus_exchange.usaspending_search import SpendingQuery, search as search_spending, award_url

def demo(*, halted=False):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now.isoformat()
    release = dict(ocid="ocds-demo-1", id="demo-1", date=stamp,
        tender=dict(status="active", title="Synthetic procurement opportunity",
        tenderPeriod=dict(endDate=(now+timedelta(days=7)).isoformat()),
        value=dict(amount=1000,currency="USD")))
    return evaluate_snapshots("demo",[release],"https://example.org/demo",stamp,now=now,halted=halted)

def run_logged(store, stop=None, archive=None, *, work=None, target="Offline screening", lead_store=None,discovery=None):
    task = uuid4().hex
    def record(state):
        store.append(dict(task_id=task,target=target,state=state,
            timestamp=datetime.now(timezone.utc).isoformat()))
    record("queued")
    if stop is not None and stop.is_set():
        record("cancelled")
        return ()
    record("running")
    try:
        started=datetime.now(timezone.utc)
        if discovery is not None and lead_store is None:
            raise ValueError("Discovery receipt requires lead archive.")
        result = (demo if work is None else work)(halted=stop.is_set() if stop is not None else False)
        if stop is not None and stop.is_set():
            record("cancelled")
            return ()
        if archive is not None:
            archive.record(tuple(item.observation for item in result))
        if lead_store is not None and type(result) is dict and result.get("format") in LEAD_FORMATS:
            if discovery is None:
                lead_store.record(result,now=datetime.now(timezone.utc),halted=stop.is_set() if stop is not None else False)
            else:
                lead_store.record(result,now=datetime.now(timezone.utc),halted=stop.is_set() if stop is not None else False,
                    discovery=dict(discovery,started_at=started,task_id=task),
                    halt_check=stop.is_set if stop is not None else None)
        elif discovery is not None:
            raise ValueError("Discovery task did not return a supported source report.")
        if stop is not None and stop.is_set():
            record("cancelled")
            return ()
    except PermissionError:
        if stop is not None and stop.is_set():
            record("cancelled")
            return ()
        record("failed")
        raise
    except Exception:
        record("failed")
        raise
    record("succeeded")
    return result

def archive_report(path, *, now, query=""):
    """Bounded historical search; screening is current, not permission."""
    if type(query) is not str or len(query) > 256:
        raise ValueError("invalid search")
    with OpportunityArchive(path) as archive:
        recent = archive.recent(now=now, limit=100)
    rows = []
    for item in recent:
        o = item.observation.opportunity
        if query.casefold() not in " ".join((o.title,o.source,o.key,o.external_id)).casefold():
            continue
        rows.append(dict(key=o.key, title=o.title, source=o.source, source_url=o.source_url,
            external_id=o.external_id, published_at=item.observation.published_at.isoformat(),
            retrieved_at=o.retrieved_at.isoformat(), deadline=o.deadline.isoformat() if o.deadline else None,
            currency=o.currency, amount=str(o.amount) if o.amount is not None else None,
            eligible_for_review=item.screening.eligible_for_review, reasons=list(item.screening.reasons)))
    return dict(scope="Historical observations; review only; no commercial authority",
        evaluated_at=now.isoformat(), search_scope="Newest 100 observations", rows=rows)

def export_report(path, report):
    Path(path).write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding="utf-8")

def main(*, data_directory=None, gui_smoke=False):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
    from tkinter.scrolledtext import ScrolledText
    from nexus_exchange.cockpit import install_cockpit, fit_geometry, smoke_cockpit, action_menu, WorkspaceViewport
    root = tk.Tk()
    root.title("Nexus Exchange | Scout preview")
    root.geometry(fit_geometry(root,1120,820))
    directory = Path(data_directory) if data_directory is not None else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NexusExchange"
    root.minsize(540, 420)
    if gui_smoke:
        root.withdraw()
    elif sys.platform == "win32":
        root.state("zoomed")
    directory.mkdir(parents=True, exist_ok=True)
    try:
        stop=RuntimeGuard(directory)
    except Exception as exc:
        if gui_smoke:
            root.destroy()
            raise
        messagebox.showerror("Nexus Exchange startup blocked",
            "Local ownership, journal or halt state could not be validated. No research started. ("+type(exc).__name__+")",parent=root)
        root.destroy()
        return
    store=stop.events
    executor = ThreadPoolExecutor(max_workers=1)
    future = None
    engaged = False
    timer = None
    next_due = None
    activity_tick = None
    updates = SimpleQueue()
    scenario_report = None
    latest_results_window = None
    def busy():
        return future is not None or stop.browser_process_pending()
    def close():
        if activity_tick is not None:
            root.after_cancel(activity_tick)
        try:
            stop.set()
        except Exception:
            pass  # In-memory halt is asserted even when persistence fails.
        executor.shutdown(wait=True, cancel_futures=True)
        stop.drain_browser_process()
        try:
            stop.close()
        finally:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    chrome=install_cockpit(root,command_deck=True)
    tabs = ttk.Notebook(chrome.content)
    tabs.pack(fill="both", expand=True, padx=6, pady=(0, 5))
    pages = {}
    for name in ("Home", "Research", "Reports", "Accounts", "Settings", "Help"):
        pages[name] = ttk.Frame(tabs, padding=(14, 10))
        tabs.add(pages[name], text=name)
    tabs.enable_traversal()
    home, research, reports, accounts, settings, help_page = pages.values()

    def heading(parent, text):
        ttk.Label(parent, text=text, font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(5, 3))

    def action_row(parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 7))
        return row

    heading(home, "Scout overview")
    ttk.Label(home, text="Engage runs Scout every hour while this window is open.",
              wraplength=440, justify="left").pack(anchor="w", pady=(0, 7))
    home_actions = action_row(home)
    cycle_status = ttk.Label(home, wraplength=490, justify="left")
    cycle_status.pack(anchor="w", pady=(0, 6))
    home_live = ActivityPanel(home)
    def open_work_folder(name):
        try:
            if not webbrowser.open(work_folder(directory, name).as_uri()):
                raise OSError()
        except (OSError, ValueError):
            messagebox.showinfo(name, f"Work folder: {directory / name}", parent=root)

    review = EngagementReports(reports, open_work_folder)
    report_actions = review.actions
    result_panel = ttk.Frame(review.tabs)
    output = ScrolledText(result_panel, width=1, height=4, wrap="word", padx=8, pady=4)
    output.pack(fill="both", expand=True)
    output.configure(state="disabled")
    feed = ActivityFeed(store.db)
    feed.settle()
    version = None
    latest_brief = None

    def refresh():
        nonlocal version
        revision = (store.db.execute("PRAGMA data_version").fetchone()[0], store.db.total_changes, next_due, latest_brief and latest_brief["finished"])
        if revision == version:
            return
        rows = with_shortlist(feed.snapshot(), latest_brief)
        if next_due is not None:
            rows.insert(0, ("next-cycle", "Pending", "Next Scout cycle",
                            "Scheduled for " + next_due.astimezone().strftime("%H:%M %Z") + " while the application is open.",
                            (next_due - timedelta(hours=1)).isoformat()))
        home_live.display(rows)
        review.activity.display(rows)
        version = revision

    def tick():
        nonlocal activity_tick
        try:
            refresh()
        finally:
            activity_tick = root.after(300, tick)
    tick()

    def select_result():
        if str(result_panel) not in review.tabs.tabs():
            review.tabs.add(result_panel, text="Task result")
        tabs.select(reports)
        review.tabs.select(result_panel)

    def clear_embedded():
        nonlocal latest_results_window
        if latest_results_window is not None and latest_results_window.winfo_exists():
            latest_results_window.destroy()
        latest_results_window = None
        output.pack(fill="both", expand=True)

    def show_result_panel():
        clear_embedded()
        select_result()

    def worker(work=None, target="Offline screening", scenario=False,discovery=None):
        local = EventStore(directory / "events.sqlite3")
        try:
            if scenario:
                with LeadStore(directory / "scout-leads.sqlite3") as leads:
                    result = run_logged(local, stop, work=work, target=target, lead_store=leads,discovery=discovery)
                    if isinstance(result, dict) and result.get("format") in LEAD_FORMATS and not stop.is_set():
                        source = LEAD_FORMATS[result["format"]][0]
                        ActivityFeed(local.db).put("manual", [finding_row(source, SOURCE_LABELS[source], r)
                                                for r in result["leads"]], datetime.now(timezone.utc))
                    return result
            with OpportunityArchive(directory / "archive.sqlite3") as archive:
                return run_logged(local, stop, archive, work=work, target=target)
        finally:
            local.close()
    def run(work=None, target="Offline screening", scenario=False,discovery=None):
        nonlocal future, scenario_report
        if stop.is_set() or busy():
            return
        launch.configure(state="disabled")
        importer.configure(state="disabled")
        simulator.configure(state="disabled")
        for button in diagnostic_buttons:
            button.configure(state="disabled")
        scenario_report = None
        exporter.configure(state="disabled")
        show_result_panel()
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("end", f"Running {target}…")
        output.configure(state="disabled")
        future = executor.submit(worker, work, target, scenario,discovery)
        poll()
    def poll():
        nonlocal future, scenario_report, latest_results_window
        refresh()
        if not future.done():
            root.after(100,poll)
            return
        output.configure(state="normal")
        output.delete("1.0","end")
        try:
            result = future.result()
            if stop.is_set():
                output.insert("end","Research halted. Task output withheld; no automatic replay.")
                return
            if type(result) is dict:
                scenario_report = result
                if result.get("format") in LEAD_FORMATS:
                    latest_results_window = show_source_results(scenario_report, embed=True)
                else:
                    output.insert("end",json.dumps(result,ensure_ascii=True,indent=2))
                exporter.configure(state="normal")
            for item in (() if type(result) is dict else result):
                o=item.observation.opportunity
                output.insert("end",f"{o.title}\nValue: {o.currency} {o.amount}\nReview eligible: {item.screening.eligible_for_review}\nReasons: {item.screening.reasons}\nHistorical observation; source assertions are unverified.\n")
        except Exception as exc:
            output.insert("end",f"Task failed: {str(exc) if type(exc) is SearchError else type(exc).__name__}")
        finally:
            refresh()
            output.configure(state="disabled")
            future = None
            if not stop.is_set():
                launch.configure(state="normal")
                importer.configure(state="normal")
                simulator.configure(state="normal")
                for button in diagnostic_buttons:
                    button.configure(state="normal")
    def show_halted(message):
        nonlocal scenario_report, engaged, timer, next_due
        engaged = False
        next_due = None
        if timer is not None:
            root.after_cancel(timer)
            timer = None
        engage_button.configure(text="Engage", state="normal")
        cycle_status.configure(text="Paused. Select Engage to start a new cycle.")
        scenario_report=None
        clear_embedded()
        exporter.configure(state="disabled")
        output.configure(state="normal")
        output.delete("1.0","end")
        output.configure(state="disabled")
        if str(result_panel) in review.tabs.tabs():
            review.tabs.forget(result_panel)
        launch.configure(state="disabled")
        importer.configure(state="disabled")
        simulator.configure(state="disabled")
        for button in diagnostic_buttons:
            button.configure(state="disabled")
        halt_status.configure(text=message)
    def halt():
        message="HALTED — new tasks blocked"
        try:
            stop.set()
        except Exception:
            message="HALTED — persistence fault; restart and recover before resuming"
        show_halted(message)
    def council_blocked():
        return stop.is_set() or busy()
    def council_action(action,plan_id):
        if council_blocked():
            raise PermissionError("Council halted or desktop worker active")
        try:
            return stop.council_action(action,plan_id)
        finally:
            if stop.is_set():
                show_halted("HALTED — Council blocked; recover interrupted attempts before explicit resume.")
    def operator_action(action,plan_id,**inputs):
        if council_blocked():
            raise PermissionError("Operator halted or desktop worker active")
        try:
            return stop.operator_action(action,plan_id,**inputs)
        finally:
            if stop.is_set():
                show_halted("HALTED — Operator blocked; review runtime before explicit resume.")
    def csv_action(action,plan_id,**inputs):
        if council_blocked():
            raise PermissionError("Operator halted or desktop worker active")
        try:
            if action in ("sim_preview","sim_create","sim_find","sim_history","sim_payment","sim_cashflow"):
                return stop.simulated_invoice_action(action[4:],plan_id,**inputs)
            if action in ("list","history","note"):
                return stop.csv_obligation_action(action,plan_id,**inputs)
            if action=="scoped_preview":
                return stop.preview_scoped_service_files(plan_id,**inputs)
            if action=="scoped_export":
                return stop.export_scoped_service_files(plan_id,**inputs)
            if action=="scoped_register":
                return stop.register_scoped_service_files(plan_id,**inputs)
            return stop.csv_file_action(action,plan_id,**inputs)
        finally:
            if stop.is_set():
                show_halted("HALTED — Operator blocked; review runtime before explicit resume.")
    diagnostic_activity = None
    def mark_activity(key, title, state, detail):
        feed.put(key, [(key, state, title, detail)], datetime.now(timezone.utc))

    def browser_diagnostic(fixture_id):
        nonlocal scenario_report, diagnostic_activity
        if council_blocked():
            return False
        show_result_panel()
        scenario_report=None
        exporter.configure(state="disabled")
        output.configure(state="normal")
        output.delete("1.0","end")
        output.insert("end","Scout owned fixture process running — no network or browser engine.")
        output.configure(state="disabled")
        try:
            stop.start_browser_process(fixture_id,confirmed=True)
        except Exception:
            if stop.is_set():
                show_halted("HALTED — Scout diagnostic could not start.")
            else:
                output.configure(state="normal")
                output.delete("1.0","end")
                output.insert("end","Scout diagnostic blocked.")
                output.configure(state="disabled")
            return False
        for button in (launch,importer,simulator,*diagnostic_buttons):
            button.configure(state="disabled")
        diagnostic_activity = uuid4().hex
        mark_activity(diagnostic_activity, "Local Scout diagnostic", "Engaged", "Running the selected offline fixture.")
        halt_status.configure(text="Scout diagnostic running — Emergency halt available.")
        root.after(25,browser_poll)
        return True
    def browser_poll():
        nonlocal diagnostic_activity
        failed = False
        try:
            report=stop.poll_browser_process()
            if report is None:
                root.after(25,browser_poll)
                return
            if not stop.is_set():
                output.configure(state="normal")
                output.delete("1.0","end")
                output.insert("end","SCOUT OFFLINE PROCESS DIAGNOSTIC — synthetic data, no browser or network.\n"
                              +json.dumps(report,ensure_ascii=True,indent=2))
                output.configure(state="disabled")
        except Exception:
            failed = not stop.is_set()
            if not stop.is_set():
                try:
                    stop.set()
                except Exception:
                    pass
        if diagnostic_activity:
            state = "Needs attention" if failed else "Stopped" if stop.is_set() else "Completed"
            mark_activity(diagnostic_activity, "Local Scout diagnostic", state, "Offline fixture process finished.")
            diagnostic_activity = None
        if stop.is_set():
            show_halted("HALTED — Scout diagnostic drained; explicit offline resume required.")
        else:
            for button in (launch,importer,simulator,*diagnostic_buttons):
                button.configure(state="normal")
            halt_status.configure(text="Offline ready — commercial actions disabled")
    def recover_council():
        if busy() or not stop.is_set():
            halt_status.configure(text="Halt and wait for workers to drain before Council recovery.")
            return None
        try:
            result=stop.recover_council()
        except Exception:
            halt_status.configure(text="HALTED — Council recovery failed; restart and review storage.")
            return None
        halt_status.configure(text=f"HALTED — {result['recovered']} Council attempts reconciled, "
            f"{result['escalated']} escalated; Resume offline explicitly.")
        return result
    def recover_advisory():
        if busy() or not stop.is_set():
            halt_status.configure(text="Halt and wait for workers to drain before advisory recovery.")
            return None
        try:
            result=stop.recover_advisory()
        except Exception:
            halt_status.configure(text="HALTED — advisory recovery failed; restart and review storage.")
            return None
        halt_status.configure(text=f"HALTED — {result['recovered']} advisory attempts reconciled, "
            f"{result['escalated']} escalated; Resume offline explicitly.")
        return result
    def resume():
        if busy():
            halt_status.configure(text="Wait for interrupted worker to finish; then resume offline.")
            return
        try:
            stop.resume()
        except Exception:
            halt_status.configure(text="HALTED — recovery or local persistence requires review")
            return
        launch.configure(state="normal")
        importer.configure(state="normal")
        simulator.configure(state="normal")
        for button in diagnostic_buttons:
            button.configure(state="normal")
        halt_status.configure(text="Offline ready — commercial actions disabled")
    def import_file():
        if stop.is_set() or busy():
            return
        path = filedialog.askopenfilename(parent=root,filetypes=[("Compiled snapshot manifest","*.json")])
        if path:
            run(partial(evaluate_file,path),target="Local compiled snapshot import")
    def import_scenario():
        if stop.is_set() or busy():
            return
        path = filedialog.askopenfilename(parent=root,filetypes=[("Deal scenario JSON","*.json")])
        if path:
            run(partial(evaluate_scenario,path,directory / "archive.sqlite3"),
                target="Offline deal simulation",scenario=True)
    def export_scenario():
        if scenario_report is None or stop.is_set():
            return
        path = filedialog.asksaveasfilename(parent=root,defaultextension=".json",
            filetypes=[("JSON","*.json")],initialfile="nexus-report.json")
        if path and not stop.is_set() and scenario_report is not None:
            try:
                export_report(path,scenario_report)
            except OSError as exc:
                messagebox.showerror("Export failed",type(exc).__name__,parent=root)
    def show_source_results(report, *, embed=False):
        if embed:
            output.pack_forget()
            window = ttk.Frame(result_panel)
            window.pack(fill="both", expand=True)
            content = ttk.Frame(window)
            content.pack(fill="both", expand=True)
        else:
            window = tk.Toplevel(root)
            content = install_cockpit(window).content
        source_format=report.get("format","nexus-sam-research-v1")
        label,link_for={
            "nexus-sam-research-v1":("SAM",notice_url),
            "nexus-ted-research-v1":("TED",ted_notice_url),
            "nexus-fts-research-v1":("UK Find a Tender",fts_notice_url),
            "nexus-cf-research-v1":("UK Contracts Finder",cf_notice_url),
            "nexus-canada-research-v1":("CanadaBuys",canada_notice_url),
            "nexus-usaspending-research-v1":("USAspending award intelligence",award_url),
        }[source_format]
        if not embed:
            window.title("Nexus Exchange | "+label+" research leads")
            window.geometry(fit_geometry(window,1050,700))
        count = sum(lead["research_candidate"] for lead in report["leads"])
        ttk.Label(content,text=f"{report['returned']} notices | {count} research candidates | {report['requests']} requests").pack(pady=6)
        ttk.Label(content,text="No lead is approved for execution. Unknown cash exposure blocks Genesis.",wraplength=1000).pack()
        if report.get("truncated"):
            ttk.Label(content,text="Search capped by request budget; additional notices not retrieved.").pack()
        if source_format=="nexus-usaspending-research-v1":
            ttk.Label(content,text="Historical prime awards, NOT open subcontracting offers. Verify actual demand.").pack()
        if source_format=="nexus-canada-research-v1":
            ttk.Label(content,text="Daily dataset snapshot; verify the original tender and exact closing timezone.").pack()
        if source_format in ("nexus-fts-research-v1","nexus-cf-research-v1"):
            ttk.Label(content,text="Historical releases only. The complete procurement lifecycle is not compiled.").pack()
        tree_area = ttk.Frame(content)
        tree_area.pack(fill="both", expand=True, padx=6, pady=3)
        tree=ttk.Treeview(tree_area,columns=("title","deadline","state"),show="headings",height=4)
        ybar = ttk.Scrollbar(tree_area, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(tree_area, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        xbar.pack(side="bottom", fill="x")
        ybar.pack(side="right", fill="y")
        for col,label,width in (("title","Opportunity",510),("deadline","Deadline / reported date",200),("state","Research status",170)):
            tree.heading(col,text=label)
            tree.column(col,width=width,anchor="w")
        tree.pack(fill="both",expand=True)
        leads = report["leads"]
        for index, lead in enumerate(leads):
            tree.insert("","end",iid=str(index),values=(lead["title"],lead["deadline"] or lead.get("earliest_deadline_date") or "Unverified",
                "Award intelligence" if source_format=="nexus-usaspending-research-v1" else "Review candidate" if lead["research_candidate"] else "Blocked"))
        details=ScrolledText(content,height=15,wrap="word",state="disabled")
        details.pack(fill="both",expand=True,padx=12,pady=8)
        def selected_index():
            selection = tree.selection()
            return int(selection[0]) if selection else None
        def display(event=None):
            index = selected_index()
            message.configure(text="")
            state = "disabled" if index is None else "normal"
            review_button.configure(state=state)
            notice_button.configure(state=state)
            details.configure(state="normal")
            details.delete("1.0","end")
            if index is None:
                details.insert("end", "Select a notice to review." if leads else
                               "This search returned no notices. In Research, open Plan a search to try a different service or source.")
            else:
                lead = leads[index]
                lines=[lead["title"],"Notice ID: "+lead["notice_id"],
                    "Source: "+lead["source_url"],"Blockers: "+", ".join(lead["blockers"]),
                    "", "TO DO — evidence required"]
                if "award_metadata" in lead:
                    lines[3:3]=[f"{k}: {v or 'Unknown'}" for k,v in lead["award_metadata"].items()]
                lines.extend("[ ] "+task["instruction"] for task in lead["todo"])
                details.insert("end","\n".join(lines))
            details.configure(state="disabled")
        def open_notice():
            index = selected_index()
            if index is not None and not stop.is_set():
                lead = leads[index]
                try:
                    webbrowser.open(link_for(lead["notice_id"]),new=2)
                except (ValueError,OSError):
                    messagebox.showerror("Browser unavailable","Unable to open official notice.",parent=window)
        def review_checklist():
            index = selected_index()
            if index is None:
                return
            try:
                if stop.is_set():
                    raise PermissionError
                archive_path = directory / "scout-leads.sqlite3"
                if not archive_path.exists():
                    raise ResultChangedError("No saved search results.")
                with ProfileStore(directory / "owner-profile.sqlite3") as profiles:
                    profile = profiles.load(halted=stop.is_set())
                with LeadStore(archive_path) as archive:
                    row = archive.resolve_result(report, index, now=datetime.now(timezone.utc),
                                                 profile=profile, halted=stop.is_set())
                checklist_window(row, window, previous=content if embed else None)
            except PermissionError:
                message.configure(text="Select Resume offline in the main window, then reopen the checklist.")
            except ResultChangedError:
                message.configure(text="This result no longer matches the saved notice. Open Research → Browse leads to review the latest copy.")
            except (ValueError, OSError, sqlite3.Error):
                message.configure(text="The checklist could not be opened. Check the saved notice in Research → Browse leads.")

        actions = ttk.Frame(content)
        actions.pack(before=tree_area, anchor="w", padx=12, pady=4)
        review_button = ttk.Button(actions, text="Review checklist", command=review_checklist)
        review_button.pack(side="left")
        notice_button = ttk.Button(actions, text="Open selected official notice", command=open_notice)
        notice_button.pack(side="left", padx=5)
        message = ttk.Label(content, wraplength=800, justify="left")
        message.pack(before=tree_area, anchor="w", padx=12)
        tree.bind("<<TreeviewSelect>>",display)
        if leads:
            tree.selection_set("0")
        display()
        return window
    def trade_routes_window():
        window = tk.Toplevel(root)
        content=install_cockpit(window).content
        window.title("Nexus Exchange | Commercial routes")
        window.geometry(fit_geometry(window,1050,700))
        ttk.Label(content,text="Commercial routes — research and compliance only",font=("Segoe UI",16)).pack(pady=8)
        ttk.Label(content,text="No route grants authority or establishes zero cash exposure.").pack()
        tree=ttk.Treeview(content,columns=("route","model","capital","gate"),show="headings",height=12)
        for key,label,width in (("route","Commercial route",300),("model","Revenue model",265),("capital","Capital status",145),("gate","Review gate",160)):
            tree.heading(key,text=label)
            tree.column(key,width=width,anchor="w")
        tree.pack(fill="x",padx=12,pady=8)
        view=ScrolledText(content,height=10,wrap="word",state="disabled")
        view.pack(fill="both",expand=True,padx=12,pady=8)
        if not stop.is_set():
            for route in ROUTES:
                tree.insert("","end",iid=route.key,values=(route.description,route.revenue_model,route.capital,route.gate))
        def show(event=None):
            selection=tree.selection()
            view.configure(state="normal")
            view.delete("1.0","end")
            try:
                if selection:
                    assessment=route_assessment(selection[0],halted=stop.is_set())
                    route=assessment["route"]
                    view.insert("end","\n".join([route.description,route.requirement,
                        "Cash exposure: unknown","Execution eligible: no","External authority: none"]))
                else:
                    view.insert("end","Select a route.")
            except PermissionError:
                view.insert("end","Halted. Resume offline research.")
            view.configure(state="disabled")
        tree.bind("<<TreeviewSelect>>",show)
        if tree.get_children():
            tree.selection_set(tree.get_children()[0])
        show()
        return window
    def trade_catalog():
        from nexus_exchange.fx_reference import CURRENCIES, fetch_reference
        from nexus_exchange.sec_company import fetch_company, normalize_cik, _declared_agent
        window = tk.Toplevel(root)
        content=install_cockpit(window).content
        window.title("Nexus Exchange | Scout global trade catalog")
        window.geometry(fit_geometry(window,1050,760))
        ttk.Label(content,text="SCOUT — Global trade sources",font=("Segoe UI",18)).pack(pady=8)
        ttk.Label(content,text="Documented sources, not connected accounts or verified revenue. SAM pilot is separate.").pack()
        filters=ttk.Frame(content)
        filters.pack(fill="x",padx=12,pady=8)
        kind=tk.StringVar(value="All")
        query=tk.StringVar(value="")
        ttk.Label(filters,text="Income type").pack(side="left")
        ttk.Combobox(filters,textvariable=kind,values=["All",*KINDS],state="readonly",width=18).pack(side="left",padx=6)
        ttk.Entry(filters,textvariable=query,width=40).pack(side="left",padx=6)
        tree=ttk.Treeview(content,columns=("name","sector","access","priority"),show="headings",height=10)
        for col,label,width in (("name","Source",265),("sector","Market",210),
                ("access","Access pathway",170),("priority","Integration priority",120)):
            tree.heading(col,text=label)
            tree.column(col,width=width,anchor="w")
        tree.pack(fill="x",padx=12,pady=6)
        details=ScrolledText(content,height=15,wrap="word",state="disabled")
        details.pack(fill="both",expand=True,padx=12,pady=8)
        rows={}
        def write_details(value):
            details.configure(state="normal")
            details.delete("1.0","end")
            details.insert("end",value)
            details.configure(state="disabled")
        def selected():
            selection=tree.selection()
            return rows.get(selection[0]) if selection else None
        def display(event=None):
            source=selected()
            if source is None:
                write_details("Select a source to inspect its documented access and required checks.")
                return
            try:
                status=readiness(source.id,halted=stop.is_set())
                tasks=source_tasks(source.id,halted=stop.is_set())
                write_details("\n".join([source.name,source.scope,"Income category: "+source.kind,
                    "Integration status: "+status["adapter_status"],"Cash exposure: unknown",
                    "External authority: none",source.evidence,"","TO DO — source prerequisites",
                    *("[ ] "+task for task in tasks)]))
            except PermissionError:
                write_details("Halted. Resume offline research to inspect this source.")
        def reload():
            rows.clear()
            for item in tree.get_children():
                tree.delete(item)
            try:
                sources=catalog(kind=None if kind.get()=="All" else kind.get(),
                    query=query.get(),halted=stop.is_set())
                for source in sources:
                    rows[source.id]=source
                    tree.insert("","end",iid=source.id,values=(source.name,source.sector,source.access,source.priority))
                if rows:
                    tree.selection_set(next(iter(rows)))
                    display()
                else:
                    write_details("No matching curated sources.")
            except (ValueError,PermissionError):
                write_details("Invalid search or halted research.")
        def open_selected(evidence=False):
            source=selected()
            if source is None:
                return
            try:
                webbrowser.open(official_url(source.id,evidence=evidence,halted=stop.is_set()),new=2)
            except (ValueError,PermissionError,OSError):
                write_details("Source opening unavailable or halted.")
        def run_ted():
            source=selected()
            if source is None or source.id!="ted":
                write_details("Select EU TED before starting its keyless search.")
                return
            if stop.is_set() or busy():
                write_details("Halted or busy. Resume or finish the current task first.")
                return
            prefix=simpledialog.askstring("TED public search",
                "CPV prefix (2–8 digits; 72 = IT services, 79 = business services).",initialvalue="72",parent=window)
            if prefix is None:
                return
            today=datetime.now(timezone.utc).date()
            request=TedQuery(prefix,today-timedelta(days=14),today)
            try:
                request.parameters(datetime.now(timezone.utc))
            except ValueError:
                write_details("Invalid CPV prefix.")
                return
            if not messagebox.askyesno("Authorize one TED search",
                    "Search public EU TED notices? Up to three read-only requests; no account, bid or spending.",
                    parent=window):
                return
            def work(*,halted):
                if halted is not False:
                    raise PermissionError("HALTED_OR_UNKNOWN")
                return search_ted(request,approved=True,halt_check=stop.is_set)
            run(work,target="TED public notice discovery",scenario=True)
            write_details("Search requested. See main dashboard for results.")
        def run_fts():
            source=selected()
            if source is None or source.id!="uk_tender":
                write_details("Select UK Find a Tender before starting its public search.")
                return
            if stop.is_set() or busy():
                write_details("Halted or busy. Resume or finish the current task first.")
                return
            if not messagebox.askyesno("Authorize one UK procurement search",
                    "Collect UK Find a Tender public releases from the last 24 hours? Up to three read-only requests; no account, bid or spending.",
                    parent=window):
                return
            now=datetime.now(timezone.utc).replace(microsecond=0)
            request=FtsQuery(now-timedelta(days=1),now)
            def work(*,halted):
                if halted is not False:
                    raise PermissionError("HALTED_OR_UNKNOWN")
                return search_fts(request,approved=True,halt_check=stop.is_set)
            run(work,target="UK public release discovery",scenario=True)
            write_details("Search requested. See main dashboard for results.")
        def run_canada():
            source=selected()
            if source is None or source.id!="canada":
                write_details("Select CanadaBuys before starting its public dataset search.")
                return
            if stop.is_set() or busy():
                write_details("Halted or busy. Resume or finish the current task first.")
                return
            keyword=simpledialog.askstring("CanadaBuys public search",
                "Filter open tender titles by keyword (no personal data).",initialvalue="software",parent=window)
            if keyword is None:
                return
            request=CanadaQuery(keyword)
            try:
                request.validated()
            except ValueError:
                write_details("Enter a keyword of 3–120 characters.")
                return
            if not messagebox.askyesno("Authorize one CanadaBuys download",
                    "Download the official daily open tender dataset? One read-only request, up to 32 MiB. No account, bid or spending.",
                    parent=window):
                return
            def work(*,halted):
                if halted is not False:
                    raise PermissionError("HALTED_OR_UNKNOWN")
                return search_canada(request,approved=True,halt_check=stop.is_set)
            run(work,target="CanadaBuys public tender discovery",scenario=True)
            write_details("Search requested. See main dashboard for results.")
        def run_spending():
            source=selected()
            if source is None or source.id!="usaspending":
                write_details("Select USAspending to research historical prime contractors.")
                return
            if stop.is_set() or busy():
                write_details("Halted or busy. Resume or finish the current task first.")
                return
            code=simpledialog.askstring("USAspending contractor research",
                "Enter a six-digit NAICS code (541511 = custom computer programming).",initialvalue="541511",parent=window)
            if code is None:
                return
            now=datetime.now(timezone.utc)
            request=SpendingQuery(code,now.date()-timedelta(days=90),now.date())
            try:
                request.parameters(now)
            except ValueError:
                write_details("Enter a valid six-digit NAICS code.")
                return
            if not messagebox.askyesno("Authorize USAspending public search",
                    "Research prime contract awards signed in the last 90 days? Up to three read-only requests. No account, outreach, bid or spending.",
                    parent=window):
                return
            def work(*,halted):
                if halted is not False:
                    raise PermissionError("HALTED_OR_UNKNOWN")
                return search_spending(request,approved=True,halt_check=stop.is_set)
            run(work,target="USAspending contractor research",scenario=True)
            write_details("Research requested. See the dashboard for results.")
        def run_cf():
            source=selected()
            if source is None or source.id!="uk_contracts":
                write_details("Select UK Contracts Finder to research official service releases.")
                return
            if stop.is_set() or busy():
                write_details("Halted or busy. Resume or finish the current task first.")
                return
            prefix=simpledialog.askstring("Contracts Finder","Local CPV prefix (72 IT services; 79 business services).",initialvalue="72",parent=window)
            if prefix is None:
                return
            hours=simpledialog.askinteger("Contracts Finder","Publication window in hours (1–24). Use a shorter window if capped.",initialvalue=6,minvalue=1,maxvalue=24,parent=window)
            if hours is None:
                return
            now=datetime.now(timezone.utc).replace(microsecond=0)
            request=CfQuery(now-timedelta(hours=hours),now,prefix)
            try:
                request.parameters(now)
            except ValueError:
                write_details("Invalid publication window or CPV prefix.")
                return
            if not messagebox.askyesno("Authorize one Contracts Finder search",
                    "Fetch one public release page, up to 50 records and 4 MiB. All stages retained for contrary evidence; CPV filter is local. No bid, account or spending.",parent=window):
                return
            def work(*,halted):
                if halted is not False:
                    raise PermissionError("HALTED_OR_UNKNOWN")
                return search_cf(request,approved=True,halt_check=stop.is_set)
            run(work,target="UK Contracts Finder public release discovery",scenario=True)
            write_details("Search requested. See main dashboard; original notice and terms require review.")
        def run_fx():
            source=selected()
            if source is None or source.id!="frankfurter":
                write_details("Select Frankfurter FX for a reference conversion.")
                return
            if stop.is_set() or busy():
                write_details("Halted or busy. Resume or finish the current task first.")
                return
            base=simpledialog.askstring("Reference FX","Source currency: "+", ".join(c for c in CURRENCIES if c!="USD"),
                                        initialvalue="EUR",parent=window)
            if base not in CURRENCIES or base=="USD":
                return
            amount=simpledialog.askstring("Reference FX","Hypothetical amount (decimal, no commas). Not sent to provider.",
                                           initialvalue="1000",parent=window)
            if amount is None:
                return
            from nexus_exchange.fx_reference import _amount
            try:
                _amount(amount)
            except ValueError:
                write_details("Invalid amount.")
                return
            if not messagebox.askyesno("Authorize one reference-rate lookup",
                    "One public Frankfurter HTTPS request for "+base+"/USD. No amount transmitted, no account, fee or payment. Reference estimate only.",parent=window):
                return
            def work(*,halted):
                if halted is not False:
                    raise PermissionError("HALTED_OR_UNKNOWN")
                return fetch_reference(base,amount,approved=True,halt_check=stop.is_set)
            run(work,target="Frankfurter reference FX estimate",scenario=True)
            write_details("Reference lookup requested. See main dashboard; no settlement or revenue claim.")
        def run_sec():
            source=selected()
            if source is None or source.id!="sec_edgar":
                write_details("Select SEC EDGAR for corporate filer research.")
                return
            if stop.is_set() or busy():
                write_details("Halted or busy. Resume or finish the current task first.")
                return
            cik=simpledialog.askstring("Atlas SEC lookup","Known company CIK (1–10 digits). Operating company only.",parent=window)
            if cik is None:
                return
            try:
                cik=normalize_cik(cik)
            except ValueError:
                write_details("Invalid company CIK.")
                return
            expected=simpledialog.askstring("Atlas SEC lookup","Optional declared company name to compare locally (not transmitted).",parent=window)
            if expected is None:
                return
            organization=simpledialog.askstring("SEC declared requester","Your real requesting business name for the required SEC User-Agent header.",parent=window)
            if organization is None:
                return
            email=simpledialog.askstring("SEC declared requester","Your real business contact email for the SEC request header. Not saved in report.",parent=window)
            if email is None:
                return
            try:
                _declared_agent(organization,email)
            except ValueError:
                write_details("Valid declared business name and contact required.")
                return
            if not messagebox.askyesno("Authorize one SEC company lookup",
                    "Send the selected company CIK and declared requester name/email to data.sec.gov? One public read-only request. No filings submitted, no contact with company, no clearance or fees.",parent=window):
                return
            def work(*,halted):
                if halted is not False:
                    raise PermissionError("HALTED_OR_UNKNOWN")
                return fetch_company(cik,organization,email,expected_name=expected.strip() or None,
                                     approved=True,halt_check=stop.is_set)
            run(work,target="Atlas SEC public company metadata research",scenario=True)
            write_details("Company research requested. See main dashboard; no identity or counterparty clearance.")
        ttk.Button(filters,text="Filter sources",command=reload).pack(side="left")
        buttons=ttk.Frame(content)
        buttons.pack(before=tree, anchor="w", padx=12, pady=4)
        ttk.Button(buttons,text="Open official source",command=open_selected).pack(side="left")
        action_menu(buttons, "Search public sources", (
            ("EU tenders", run_ted), ("UK Find a Tender", run_fts), ("CanadaBuys", run_canada),
            ("USAspending awards", run_spending), ("UK Contracts Finder", run_cf),
        )).pack(side="left", padx=4)
        action_menu(buttons, "Reference tools", (
            ("Commercial routes", trade_routes_window), ("Company filings", run_sec),
            ("Exchange rates", run_fx), ("Source documentation", lambda: open_selected(True)),
        )).pack(side="left")
        tree.bind("<<TreeviewSelect>>",display)
        reload()
        return window
    def revenue_workspace():
        window = tk.Toplevel(root)
        content=install_cockpit(window).content
        window.title("Nexus Exchange | Scout revenue pathways")
        window.geometry(fit_geometry(window,900,760))
        ttk.Label(content,text="SCOUT — Revenue pathways",font=("Segoe UI",18)).pack(pady=10)
        ttk.Label(content,text="Planning only. Budget entries do not connect a bank or authorize spending.").pack()
        settings = ttk.Frame(content)
        settings.pack(fill="x",padx=15,pady=10)
        mode = tk.StringVar(value=Mode.GENESIS.value)
        source = tk.StringVar(value=SOURCES[0].key)
        budget = tk.StringVar(value="0")
        exposure = tk.StringVar(value="")
        for i,(label,var,values) in enumerate((
                ("Pathway",mode,[m.value for m in Mode]),
                ("Official source",source,[s.key for s in SOURCES]),
                ("USD planning budget",budget,None),
                ("USD maximum cash exposure (blank = unknown)",exposure,None))):
            ttk.Label(settings,text=label).grid(row=i,column=0,sticky="w",pady=3)
            widget=ttk.Combobox(settings,textvariable=var,values=values,state="readonly") if values else ttk.Entry(settings,textvariable=var)
            widget.grid(row=i,column=1,sticky="ew",padx=8)
        settings.columnconfigure(1,weight=1)
        prerequisites = ttk.Label(content,wraplength=850,justify="left")
        prerequisites.pack(fill="x",padx=15,pady=6)
        flags={key:tk.BooleanVar(value=False) for key,_ in CHECKS}
        checklist=ttk.LabelFrame(content,text="To do — owner assertions only, independent verification required")
        checklist.pack(fill="x",padx=15,pady=8)
        for key,instruction in CHECKS:
            ttk.Checkbutton(checklist,text=instruction,variable=flags[key]).pack(anchor="w",padx=6,pady=3)
        result=ttk.Label(content,wraplength=850,justify="left")
        result.pack(fill="x",padx=15,pady=8)
        def refresh_plan():
            try:
                selected=next(s for s in SOURCES if s.key==source.get())
                prerequisites.configure(text=selected.title+"\n"+"\n".join("• "+p for p in selected.prerequisites))
                plan=plan_lead(Mode(mode.get()),source.get(),budget=budget.get(),
                    exposure=exposure.get() or None,confirmed=tuple(k for k,v in flags.items() if v.get()),
                    halted=stop.is_set())
                result.configure(text=("Checklist entered — independent lead review required." if plan.ready_for_review
                    else "Blocked: "+", ".join(plan.reasons))+"\nExternal authority: none.")
            except (ValueError,PermissionError) as exc:
                result.configure(text="Blocked: "+str(exc))
        procurement_type = tk.StringVar(value="Combined synopsis/solicitation")
        selector = ttk.Frame(content)
        selector.pack(before=prerequisites, fill="x",padx=15,pady=4)
        ttk.Label(selector,text="SAM notice type").pack(side="left")
        ttk.Combobox(selector,textvariable=procurement_type,values=["Combined synopsis/solicitation","Solicitation"],state="readonly",width=32).pack(side="left",padx=8)
        def reset_checks(*unused):
            for flag in flags.values():
                flag.set(False)
            if mode.get()==Mode.GENESIS.value and budget.get()!="0":
                budget.set("0")
            refresh_plan()
        def open_source():
            # Explicit owner click opens only a fixed official homepage in their browser.
            # No automated fetch, login, form filling or credential handling.
            if stop.is_set():
                result.configure(text="Halted. Resume before opening Scout sources.")
                return
            try:
                webbrowser.open(source_url(source.get()),new=2)
            except (ValueError,OSError) as exc:
                result.configure(text="Browser unavailable: "+type(exc).__name__)
        for var in (source,mode,budget,exposure):
            var.trace_add("write",reset_checks)
        for flag in flags.values():
            flag.trace_add("write",lambda *unused:refresh_plan())
        def run_sam():
            if stop.is_set() or busy():
                result.configure(text="Halted or busy. Resume or finish the current task first.")
                return
            if source.get()!="sam":
                result.configure(text="Choose SAM as the official source first.")
                return
            title=simpledialog.askstring("SAM read-only search","Enter a public opportunity title keyword (no personal data).",parent=window)
            if not title:
                return
            today=datetime.now(timezone.utc).date()
            query=Query(today-timedelta(days=14),today,title,
                "o" if procurement_type.get()=="Solicitation" else "k")
            try:
                query.parameters(datetime.now(timezone.utc))
            except ValueError:
                result.configure(text="Invalid search keyword.")
                return
            if not messagebox.askyesno("Authorize one SAM search",
                    "Send this search to the official SAM.gov API? Up to 3 requests using your API quota. No bid, submission or spending.\n\nKeyword: "+title,parent=window):
                return
            key=simpledialog.askstring("SAM API key","Enter your own SAM public API key for this search. It will not be saved.",show="*",parent=window)
            if not key:
                return
            def work(*,halted):
                if halted is not False:
                    raise PermissionError("HALTED_OR_UNKNOWN")
                return search_sam(query,key,approved=True,halt_check=stop.is_set)
            run(work,target="SAM read-only notice discovery",scenario=True)
            result.configure(text="Search requested. See the main dashboard for results.")
        buttons=ttk.Frame(content)
        buttons.pack(before=settings, anchor="w", padx=15, pady=4)
        ttk.Button(buttons,text="Open official source",command=open_source).pack(side="left")
        ttk.Button(buttons,text="Search SAM (read only)",command=run_sam).pack(side="left")
        ttk.Button(buttons,text="Refresh checklist",command=refresh_plan).pack(side="left")
        ttk.Button(buttons,text="Global trade catalog",command=trade_catalog).pack(side="left")
        refresh_plan()
        return window
    def planned_discovery(plan,option_id,*,approved=None,api_key=None):
        if council_blocked() or approved is not True:
            raise PermissionError("Current public-search consent and idle runtime required.")
        profile=load_profile(directory,halt_check=stop.is_set)
        row,_=resolve_query(plan,option_id,profile,now=datetime.now(timezone.utc),halted=stop.is_set())
        def work(*,halted):
            if halted is not False:
                raise PermissionError("HALTED_OR_UNKNOWN")
            current=load_profile(directory,halt_check=stop.is_set)
            return execute_discovery(plan,option_id,current,now=datetime.now(timezone.utc),
                approved=approved,halt_check=stop.is_set,api_key=api_key)
        if council_blocked():
            raise PermissionError("Runtime changed before search.")
        run(work,target="Capability discovery: "+row["source"]+" / "+plan["service_label"],scenario=True,
            discovery=dict(plan=plan,option_id=option_id,profile=profile))
        return True
    def discovery_window(*,smoke=False):
        return open_discovery_window(root,directory=directory,halt_check=stop.is_set,
            blocked_check=council_blocked,launch=planned_discovery,edit_profile=owner_profile_window,smoke=smoke)
    def owner_profile_window(*, parent=root, on_changed=None):
        window = tk.Toplevel(parent)
        if on_changed is not None:
            window.transient(parent)
        content=install_cockpit(window).content
        window.title("Nexus Exchange | Search settings")
        window.geometry(fit_geometry(window,720,490))
        heading(content, "Search settings")
        buttons = action_row(content)
        message = ttk.Label(content, wraplength=600, justify="left")
        message.pack(fill="x", pady=4)
        sections = ttk.Notebook(content)
        sections.pack(fill="both", expand=True, padx=6, pady=5)
        basics = ttk.Frame(sections, padding=10)
        advanced = ttk.Frame(sections, padding=10)
        sections.add(basics, text="Hours and sources")
        sections.add(advanced, text="Budget and filters")
        sections.enable_traversal()
        values = {key: tk.StringVar(master=window) for key in
                  ("mode", "budget", "hours_per_week", "naics", "cpv", "keywords")}
        ttk.Label(basics, text="Available hours per week (0–168)").pack(anchor="w")
        ttk.Entry(basics, name="hours", textvariable=values["hours_per_week"], width=8).pack(anchor="w", pady=4)
        source_box = ttk.LabelFrame(basics, text="Sources to include", padding=8)
        source_box.pack(fill="x", pady=6)
        flags = {source: tk.BooleanVar(master=window) for source in PROFILE_SOURCES}
        for i, (source, flag) in enumerate(flags.items()):
            ttk.Checkbutton(source_box, text=SOURCE_LABELS[source], variable=flag).grid(
                row=i//2, column=i%2, sticky="w", padx=4, pady=2)
        ttk.Label(basics, text="SAM.gov asks for your API key when you run a search. EU TED and UK Contracts Finder use the CPV codes you enter under Budget and filters.",
                  wraplength=500, justify="left").pack(anchor="w", pady=4)
        fields = (("Operating pathway", "mode"), ("Planning budget in USD", "budget"),
                  ("NAICS industry codes (6 digits)", "naics"), ("CPV procurement codes (2–8 digits)", "cpv"),
                  ("Service keywords", "keywords"))
        for i, (label, key) in enumerate(fields):
            ttk.Label(advanced, text=label).grid(row=i, column=0, sticky="w", pady=4)
            widget = (ttk.Combobox(advanced, textvariable=values[key], values=["genesis","catalyst"],
                                   state="readonly") if key == "mode" else ttk.Entry(advanced, textvariable=values[key]))
            widget.grid(row=i, column=1, sticky="ew", padx=6)
        advanced.columnconfigure(1, weight=1)
        ttk.Label(advanced, text="Genesis uses a zero planning budget. Separate multiple codes or keywords with commas.",
                  wraplength=460, justify="left").grid(row=len(fields), columnspan=2, sticky="w", pady=5)
        def split(key):
            return [v.strip() for v in values[key].get().split(",") if v.strip()]
        def populate(profile):
            if profile is None:
                profile=dict(mode="genesis",budget="0",hours_per_week=0,naics=[],cpv=[],keywords=[],sources=[])
            for key,var in values.items():
                v=profile[key]
                var.set(", ".join(v) if type(v) is list else str(v))
            for source,flag in flags.items():
                flag.set(source in profile["sources"])
        loaded_revision = None
        def load():
            nonlocal loaded_revision
            save_button.state(["disabled"])
            clear_button.state(["disabled"])
            try:
                if stop.is_set():
                    raise PermissionError
                with ProfileStore(directory / "owner-profile.sqlite3") as store:
                    profile = store.load(halted=stop.is_set())
                loaded_revision = profile_revision(profile) if profile is not None else None
                populate(profile)
                save_button.state(["!disabled"])
                if profile is not None:
                    clear_button.state(["!disabled"])
                message.configure(text="Preferences loaded." if profile else "Enter your available hours and select the sources you want to search.")
            except PermissionError:
                message.configure(text="Select Resume offline in the main window, then Reload.")
            except (ValueError, OSError, sqlite3.Error):
                message.configure(text="Preferences could not be read. Check local storage, then Reload.")

        def finish_change():
            if on_changed is not None:
                window.destroy()
                on_changed()

        def save():
            nonlocal loaded_revision
            if stop.is_set():
                message.configure(text="Select Resume offline in the main window before saving.")
                return
            try:
                hours = int(values["hours_per_week"].get())
                if not 0 <= hours <= 168:
                    raise ValueError
            except ValueError:
                sections.select(basics)
                message.configure(text="Enter a whole number of hours between 0 and 168.")
                return
            try:
                profile = dict(mode=values["mode"].get(), budget=values["budget"].get(), hours_per_week=hours,
                    naics=split("naics"), cpv=split("cpv"), keywords=[x.casefold() for x in split("keywords")],
                    sources=[source for source, flag in flags.items() if flag.get()])
                with ProfileStore(directory / "owner-profile.sqlite3") as store:
                    loaded_revision = store.save(profile, halted=stop.is_set(), expected_revision=loaded_revision)
            except ProfileChangedError:
                message.configure(text="Saved preferences have changed or could not be verified. Reload before saving.")
                return
            except ValueError:
                sections.select(advanced)
                message.configure(text="Check the planning budget, code lengths and duplicate entries under Budget and filters.")
                return
            except (PermissionError, OSError, sqlite3.Error):
                message.configure(text="Preferences could not be saved. Check local storage and the halt status.")
                return
            clear_button.state(["!disabled"])
            message.configure(text="Preferences saved.")
            finish_change()

        def clear():
            if stop.is_set():
                message.configure(text="Select Resume offline in the main window before clearing preferences.")
                return
            if messagebox.askyesno("Clear local profile","Remove saved planning preferences?",parent=window):
                try:
                    with ProfileStore(directory / "owner-profile.sqlite3") as store:
                        store.clear(halted=stop.is_set(), expected_revision=loaded_revision)
                except ProfileChangedError:
                    message.configure(text="Saved preferences have changed or could not be verified. Reload before clearing.")
                    return
                except ValueError:
                    message.configure(text="Saved preferences could not be read. Check local storage.")
                    return
                except (PermissionError, OSError, sqlite3.Error):
                    message.configure(text="Preferences could not be cleared. Check local storage and the halt status.")
                    return
                load()
                finish_change()
        save_button = ttk.Button(buttons, text="Save and return" if on_changed else "Save preferences", command=save)
        save_button.pack(side="left", padx=4)
        ttk.Button(buttons, text="Reload", command=load).pack(side="left", padx=4)
        clear_button = ttk.Button(buttons, text="Clear profile", command=clear)
        clear_button.pack(side="left", padx=4)
        load()
        return window
    def checklist_window(row,parent,*,smoke=False,previous=None):
        initial=context_for(row)
        def current_context():
            if stop.is_set():
                raise PermissionError("HALTED")
            with ProfileStore(directory / "owner-profile.sqlite3") as profiles:
                profile=profiles.load(halted=stop.is_set())
            with LeadStore(directory / "scout-leads.sqlite3") as leads:
                result=leads.browse(now=datetime.now(timezone.utc),source=initial["source"],
                    lead_key=initial["lead_key"],profile=profile,limit=1,halted=stop.is_set())
            if not result["leads"] or context_for(result["leads"][0])!=initial:
                raise ValueError("Observation or profile changed. Refresh Scout history.")
            return initial
        current_context()
        if previous is None:
            window = tk.Toplevel(parent)
            content = install_cockpit(window).content
            window.title("Nexus Exchange | Persistent To Do")
            window.geometry(fit_geometry(window, 1000, 720))
        else:
            previous.pack_forget()
            window = ttk.Frame(parent, name="checklist")
            window.pack(fill="both", expand=True)
            def return_to_results():
                window.destroy()
                previous.pack(fill="both", expand=True)
            ttk.Button(window, text="Back to notices", command=return_to_results).pack(anchor="w")
            content = WorkspaceViewport(window).content
        ttk.Label(content,text="TO DO — Owner review notes",font=("Segoe UI",18)).pack(pady=8)
        ttk.Label(content,text=row["title"],wraplength=940).pack(padx=12)
        ttk.Label(content,text="Evidence noted means an owner assertion, NOT verification or authorization.",
            wraplength=940).pack(pady=4)
        summary=ttk.Label(content)
        summary.pack()
        tree=ttk.Treeview(content,columns=("instruction","state"),show="headings",height=9)
        tree.heading("instruction",text="Required check")
        tree.heading("state",text="Owner review state")
        tree.column("instruction",width=730,anchor="w")
        tree.column("state",width=180,anchor="w")
        tree.pack(fill="x",padx=12,pady=8)
        instruction=ttk.Label(content,wraplength=940,justify="left")
        instruction.pack(fill="x",padx=12,pady=4)
        editor=ttk.Frame(content)
        editor.pack(before=tree, fill="x",padx=12,pady=4)
        labels={"pending":"Pending","needs_followup":"Needs follow-up","evidence_noted":"Evidence noted"}
        values={v:k for k,v in labels.items()}
        state=tk.StringVar(value=labels["pending"])
        reference=tk.StringVar(value="")
        ttk.Label(editor,text="State").grid(row=0,column=0,sticky="w")
        ttk.Combobox(editor,textvariable=state,values=list(labels.values()),state="readonly",width=22).grid(row=0,column=1,sticky="w")
        ttk.Label(editor,text="Evidence reference (no credentials or personal data)").grid(row=1,column=0,sticky="w",pady=6)
        ttk.Entry(editor,textvariable=reference).grid(row=1,column=1,sticky="ew",padx=8)
        editor.columnconfigure(1,weight=1)
        message=ttk.Label(content,wraplength=940,justify="left")
        message.pack(fill="x",padx=12,pady=6)
        data=None
        tasks={}
        def select(event=None):
            selection=tree.selection()
            task=tasks.get(selection[0]) if selection else None
            if task:
                instruction.configure(text=task["instruction"])
                state.set(labels[task["state"]])
                reference.set(task["reference"])
        def populate(result,selected=None):
            nonlocal data
            data=result
            tasks.clear()
            for item in tree.get_children():
                tree.delete(item)
            for task in result["tasks"]:
                tasks[task["key"]]=task
                tree.insert("","end",iid=task["key"],values=(task["instruction"],labels[task["state"]]))
            summary.configure(text=f"{result['evidence_noted']} / {result['total']} evidence references noted — independent verification pending")
            if tasks:
                tree.selection_set(selected if selected in tasks else next(iter(tasks)))
                select()
        def reload():
            nonlocal data
            data=None
            try:
                with ChecklistStore(directory / "scout-todo.sqlite3") as store:
                    populate(store.load(current_context(),halted=stop.is_set()))
                message.configure(text="Local review notes loaded.")
            except Exception:
                message.configure(text="Unable to load current context. Refresh Scout history or resume.")
        def save():
            selection=tree.selection()
            if not selection or data is None:
                return
            try:
                with ChecklistStore(directory / "scout-todo.sqlite3") as store:
                    result=store.save(current_context(),selection[0],values[state.get()],reference.get(),
                        now=datetime.now(timezone.utc),expected_revision=data["revision"],halted=stop.is_set())
                populate(result,selection[0])
                message.configure(text="Saved locally. No commercial authority granted.")
            except (ValueError,PermissionError) as exc:
                message.configure(text=str(exc))
            except Exception:
                message.configure(text="Save failed. Reload before retrying.")
        def pick_evidence(path=None):
            if not tree.selection() or data is None:
                return False
            try:
                current_context()
                if path is None:
                    path=filedialog.askopenfilename(parent=window,title="Select local evidence file")
                if not path:
                    return False
                ref=fingerprint(path,halted=stop.is_set(),halt_check=stop.is_set)
                current_context()
                state.set(labels["evidence_noted"])
                reference.set(ref)
                message.configure(text="File fingerprint created. Save selected task to retain it. Contents and path are not stored.")
                return True
            except (EvidenceError,PermissionError,ValueError):
                message.configure(text="File fingerprint unavailable, invalid or context changed. Reload and select a local file.")
                return False
            except Exception:
                message.configure(text="Unable to fingerprint file.")
                return False
        def check_evidence(path=None):
            selection=tree.selection()
            if not selection or data is None:
                return None
            key=selection[0]
            try:
                with ChecklistStore(directory / "scout-todo.sqlite3") as store:
                    latest=store.load(current_context(),halted=stop.is_set())
                if latest["revision"]!=data["revision"]:
                    raise ValueError("Checklist changed")
                saved=next(t for t in latest["tasks"] if t["key"]==key)
                if saved["state"]!="evidence_noted" or not saved["reference"].startswith("sha256:"):
                    message.configure(text="Save a file fingerprint for this task first.")
                    return None
                if path is None:
                    path=filedialog.askopenfilename(parent=window,title="Reselect evidence file to check")
                if not path:
                    return None
                result=verify_reference(path,saved["reference"],halted=stop.is_set(),halt_check=stop.is_set)
                with ChecklistStore(directory / "scout-todo.sqlite3") as store:
                    again=store.load(current_context(),halted=stop.is_set())
                if again["revision"]!=latest["revision"]:
                    raise ValueError("Checklist changed")
                message.configure(text=("Byte fingerprint matches saved reference." if result["byte_match"]
                    else "File differs from saved fingerprint.")+" Content accuracy, origin and authorization remain unverified.")
                return result
            except (EvidenceError,PermissionError,ValueError):
                message.configure(text="Check unavailable or evidence/context changed. Reload before retrying.")
                return None
            except Exception:
                message.configure(text="Unable to check local evidence.")
                return None
        buttons=ttk.Frame(content)
        buttons.pack(before=tree, anchor="w", padx=12, pady=4)
        ttk.Button(buttons,text="Fingerprint evidence file",command=pick_evidence).pack(side="left",padx=5)
        ttk.Button(buttons,text="Check saved fingerprint",command=check_evidence).pack(side="left",padx=5)
        ttk.Button(buttons,text="Save selected task",command=save).pack(side="left")
        ttk.Button(buttons,text="Reload",command=reload).pack(side="left",padx=8)
        tree.bind("<<TreeviewSelect>>",select)
        reload()
        if smoke:
            if data is None or not tasks:
                raise RuntimeError("checklist GUI failed to load")
            synthetic=directory / "aegis-smoke-evidence.txt"
            synthetic.write_bytes(b"Synthetic evidence fixture")
            if not pick_evidence(synthetic):
                raise RuntimeError("evidence GUI failed to fingerprint")
            save()
            if data["evidence_noted"]!=1:
                raise RuntimeError("checklist GUI failed to save")
            reload()
            if data is None or data["evidence_noted"]!=1:
                raise RuntimeError("checklist GUI failed to reload")
            checked=check_evidence(synthetic)
            if checked is None or not checked["byte_match"] or checked["independently_verified"]:
                raise RuntimeError("evidence GUI failed to compare saved fingerprint")
            synthetic.unlink()
        return window
    def ranked_matrix():
        return open_ranking_window(root,directory=directory,halt_check=stop.is_set,review_tasks=checklist_window,
            council_action=council_action,council_blocked=council_blocked,
            operator_action=operator_action,operator_blocked=council_blocked,csv_action=csv_action)
    def browse_leads():
        window = tk.Toplevel(root)
        content=install_cockpit(window).content
        window.title("Nexus Exchange | Unified Scout history")
        window.geometry(fit_geometry(window,1050,720))
        ttk.Label(content,text="SCOUT — Historical lead memory",font=("Segoe UI",18)).pack(pady=8)
        ttk.Label(content,text="Saved observations only. Owner profile changes review order, never eligibility.").pack()
        filters=ttk.Frame(content)
        filters.pack(fill="x",padx=12,pady=8)
        source=tk.StringVar(value="All")
        search=tk.StringVar(value="")
        ttk.Combobox(filters,textvariable=source,values=["All",*PROFILE_SOURCES],
            state="readonly",width=18).pack(side="left",padx=5)
        ttk.Entry(filters,textvariable=search,width=40).pack(side="left",padx=5)
        summary=ttk.Label(content)
        summary.pack()
        tree=ttk.Treeview(content,columns=("source","title","fit","deadline"),show="headings",height=10)
        for col,label,width in (("source","Source",105),("title","Notice",420),
                ("fit","Review priority",235),("deadline","Reported deadline",175)):
            tree.heading(col,text=label)
            tree.column(col,width=width,anchor="w")
        tree.pack(fill="x",padx=12,pady=6)
        details=ScrolledText(content,height=15,wrap="word",state="disabled")
        details.pack(fill="both",expand=True,padx=12,pady=8)
        report=None
        rows={}
        def write(value):
            details.configure(state="normal")
            details.delete("1.0","end")
            details.insert("end",value)
            details.configure(state="disabled")
        def selected():
            selection=tree.selection()
            return rows.get(selection[0]) if selection else None
        def display(event=None):
            row=selected()
            if row is not None:
                write("\n".join([row["title"],row["source_url"],"Historical only; execution blocked.",
                    *(f"{k}: {v or 'Unknown'}" for k,v in row.get("award_metadata",{}).items()),
                    "Retrieved: "+row["retrieved_at"],
                    "Profile: "+row.get("profile_fit",{}).get("reason","No saved profile"),
                    "Verification blockers: "+", ".join(row["blockers"]),"","TO DO",
                    *("[ ] "+t["instruction"] for t in row["todo"])]))
        def reload():
            nonlocal report
            report=None
            rows.clear()
            for item in tree.get_children():
                tree.delete(item)
            try:
                with ProfileStore(directory / "owner-profile.sqlite3") as profiles:
                    profile=profiles.load(halted=stop.is_set())
                with LeadStore(directory / "scout-leads.sqlite3") as store:
                    report=store.browse(now=datetime.now(timezone.utc),profile=profile,
                        source=None if source.get()=="All" else source.get(),
                        query=search.get(),halted=stop.is_set())
                for i,row in enumerate(report["leads"]):
                    rows[str(i)]=row
                    tree.insert("","end",iid=str(i),values=(row["source"],row["title"],
                        row.get("profile_fit",{}).get("reason","Unranked"),row["deadline"] or row["earliest_deadline_date"] or "Unverified"))
                summary.configure(text=f"{report['returned']} shown / {report['matched']} matching historical notices")
                if rows:
                    tree.selection_set("0")
                    display()
                else:
                    write("No saved discoveries match.")
            except (ValueError,PermissionError,OSError) as exc:
                summary.configure(text="Archive unavailable")
                write(type(exc).__name__)
            except Exception as exc:
                summary.configure(text="Archive unavailable")
                write(type(exc).__name__)
        def open_selected():
            row=selected()
            if row is not None and not stop.is_set():
                try:
                    _,link_for=LEAD_FORMATS[row["format"]]
                    webbrowser.open(link_for(row["notice_id"]),new=2)
                except (ValueError,OSError):
                    write("Official notice unavailable.")
        def export():
            if report is None or stop.is_set():
                return
            path=filedialog.asksaveasfilename(parent=window,defaultextension=".json",
                filetypes=[("JSON","*.json")],initialfile="nexus-scout-history.json")
            if path and not stop.is_set() and report is not None:
                try:
                    export_report(path,report)
                except OSError as exc:
                    messagebox.showerror("Export failed",type(exc).__name__,parent=window)
        ttk.Button(filters,text="Filter / refresh",command=reload).pack(side="left",padx=5)
        buttons=ttk.Frame(content)
        buttons.pack(before=tree, anchor="w", padx=12, pady=4)
        ttk.Button(buttons,text="Open official notice",command=open_selected).pack(side="left")
        def review_tasks():
            row=selected()
            if row is not None:
                try:
                    checklist_window(row,window)
                except (ValueError,PermissionError):
                    write("Checklist context changed or halted. Refresh history.")
                except Exception:
                    write("Checklist unavailable.")
        ttk.Button(buttons,text="Review To Do",command=review_tasks).pack(side="left",padx=5)
        def review_scenarios():
            row=selected()
            if row is not None:
                try:
                    open_scenario_window(window,row,directory=directory,halt_check=stop.is_set,
                        council_action=council_action,council_blocked=council_blocked,
                        operator_action=operator_action,operator_blocked=council_blocked,csv_action=csv_action)
                except (ValueError,PermissionError):
                    write("Save an owner profile and refresh Scout history; scenario context changed or research halted.")
                except Exception:
                    write("Scenario workspace unavailable.")
        ttk.Button(buttons,text="Plan scenario",command=review_scenarios).pack(side="left",padx=5)
        ttk.Button(buttons,text="Ranked Matrix",command=ranked_matrix).pack(side="left",padx=5)
        ttk.Button(buttons,text="Export history JSON",command=export).pack(side="left",padx=5)
        ttk.Button(buttons,text="Owner profile",command=owner_profile_window).pack(side="left",padx=5)
        tree.bind("<<TreeviewSelect>>",display)
        reload()
        return window
    archive_page = None
    def browse_archive():
        nonlocal archive_page
        if archive_page is not None and archive_page.winfo_exists():
            tabs.select(reports)
            review.tabs.select(archive_page)
            return archive_page
        window = archive_page = ttk.Frame(review.tabs, padding=(5, 3))
        review.tabs.add(window, text="Archive")
        tabs.select(reports)
        review.tabs.select(window)
        filters = ttk.Frame(window)
        filters.pack(fill="x")
        ttk.Label(filters, text="Search archive").pack(side="left")
        query = tk.StringVar()
        ttk.Entry(filters, textvariable=query, width=15).pack(side="left", fill="x", expand=True, padx=4)
        view = ScrolledText(window, wrap="word", width=1, height=4)
        view.pack(fill="both", expand=True, pady=4)
        snapshot = None
        displayed = None
        def render(*_):
            nonlocal displayed
            displayed = None
            if snapshot is None:
                value = "Archive unavailable. Resume research and refresh the archive."
            else:
                needle = query.get().casefold().strip()
                rows = [r for r in snapshot["rows"] if any(needle in str(r[k]).casefold()
                        for k in ("title", "source", "key", "external_id"))]
                displayed = dict(snapshot, rows=rows)
                lines = [f"{len(rows)} matches in the latest {len(snapshot['rows'])} historical observations."]
                for r in rows:
                    lines.extend(("", r["title"], r["source"] + " · " + r["external_id"],
                                  "Reported deadline: " + (r["deadline"] or "Unknown"), r["source_url"]))
                value = "\n".join(lines)
            view.configure(state="normal")
            view.delete("1.0", "end")
            view.insert("end", value)
            view.configure(state="disabled")
        def reload():
            nonlocal snapshot
            try:
                snapshot = None if stop.is_set() else archive_report(directory / "archive.sqlite3", now=datetime.now(timezone.utc))
            except (OSError, ValueError, sqlite3.Error):
                snapshot = None
            render()
        def export():
            if displayed is None or stop.is_set():
                return
            path = filedialog.asksaveasfilename(parent=root, defaultextension=".json",
                      filetypes=[("JSON","*.json")], initialfile="nexus-history.json")
            if path and not stop.is_set():
                try:
                    export_report(path, displayed)
                except OSError as exc:
                    messagebox.showerror("Export failed", type(exc).__name__, parent=root)
        ttk.Button(filters, text="Refresh", command=reload).pack(side="left")
        ttk.Button(filters, text="Export JSON", command=export).pack(side="left", padx=3)
        query.trace_add("write", render)
        reload()
        return window

    def read_brief():
        try:
            with (directory / engagement.BRIEF).open(encoding="utf-8") as handle:
                return json.loads(handle.read(1024 * 1024))
        except FileNotFoundError:
            return None

    def summarize(brief):
        found = sum(item["found"] for item in brief["sources"])
        jobs = brief["jobs"]
        return (f"{brief['status']} · Notices {found} · Shortlisted {len(brief['shortlist'])}"
                f" · Files created {jobs['produced']} · Files held {jobs['held']}")

    def open_brief():
        tabs.select(reports)
        review.tabs.select(review.summary)

    def start_cycle():
        nonlocal future, timer, next_due
        timer = None
        if not engaged or stop.is_set():
            return
        if busy():
            timer = root.after(1000, start_cycle)
            return
        next_due = None
        kwargs = {}
        if gui_smoke:
            def fixture_search(source, *args):
                if not release_search.wait(10):
                    raise RuntimeError("Timed out waiting for the live GUI fixture")
                fmt = {"uk_tender": "nexus-fts-research-v1", "canada": "nexus-canada-research-v1"}[source]
                return dict(format=fmt, returned=0, leads=[], truncated=False, page_sha256=["0"*64])
            kwargs["default_search"] = fixture_search
        future = executor.submit(engagement.cycle, directory, stop.is_set, updates.put, **kwargs)
        root.after(100, poll_cycle)

    def poll_cycle():
        nonlocal future, timer, next_due, latest_brief
        while True:
            try:
                stage = updates.get_nowait()
            except Empty:
                break
            if engaged:
                cycle_status.configure(text=stage + "…")
        if not future.done():
            root.after(100, poll_cycle)
            return
        try:
            brief = future.result()
            next_status = summarize(brief)
            review.display(brief)
            latest_brief = brief
        except Exception:
            next_status = "Cycle interrupted. Review Reports for the recorded task status."
        future = None
        refresh()
        if engaged and not stop.is_set():
            next_due = datetime.now(timezone.utc) + timedelta(hours=1)
            next_time = next_due.astimezone().strftime("%H:%M")
            cycle_status.configure(text=next_status + f"\nNext search at {next_time} local time.")
            refresh_accounts()
            timer = root.after(3600000, start_cycle)
            refresh()

    def engage():
        nonlocal engaged
        if engaged:
            return
        if busy():
            cycle_status.configure(text="A task is finishing. Select Engage when it is done.")
            return
        resume()
        if stop.is_set():
            return
        engaged = True
        engage_button.configure(text="Engaged", state="disabled")
        halt_status.configure(text="Scout is engaged · Emergency halt stops this session.")
        cycle_status.configure(text="Starting baseline research…")
        start_cycle()

    def account_task(work, done):
        nonlocal future
        if busy():
            done("A task is running. Try again after it finishes.")
            return False
        resume()
        if stop.is_set():
            done("Account setup is paused pending runtime recovery.")
            return False
        if engaged:
            halt_status.configure(text="Scout is engaged · Account setup in progress.")
        account_id = uuid4().hex
        mark_activity(account_id, "Account connection", "Engaged", "Waiting for the provider or local account setup.")
        future = executor.submit(work, stop.is_set)
        def finish():
            nonlocal future
            if not future.done():
                root.after(125, finish)
                return
            try:
                message = future.result()
                state = "Completed"
            except Exception:
                state = "Needs attention"
                message = "Connection incomplete. Check provider access in Accounts and reconnect if needed."
            future = None
            mark_activity(account_id, "Account connection", "Stopped" if stop.is_set() else state,
                          "See Accounts for the connection status.")
            done("Account setup stopped." if stop.is_set() else message)
            if engaged:
                halt_status.configure(text="Scout is engaged · Emergency halt stops this session.")
        root.after(125, finish)
        return True

    safety_buttons = ttk.Frame(chrome.safety)
    safety_buttons.pack(fill="x")
    ttk.Label(safety_buttons, text="Nexus Exchange", font=("Segoe UI", 15, "bold")).pack(side="left")
    halt_button = ttk.Button(safety_buttons, text="Emergency halt", command=halt, style="Halt.TButton")
    halt_button.pack(side="right")
    resume_button = ttk.Button(settings, text="Resume offline", command=resume)
    # Advanced manual tools can be enabled separately in Settings.
    halt_status = ttk.Label(chrome.safety, text="Ready · Select Engage on Home.")
    halt_status.pack(fill="x", pady=(2, 0))
    if stop.recovered_count or stop.council_recovered_count or stop.advisory_recovered_count:
        halt_status.configure(text=f"Halted · Recovered {stop.recovered_count} tasks, "
                              f"{stop.council_recovered_count} Council and {stop.advisory_recovered_count} advisory attempts. Select Engage on Home.")
    chrome.safety.bind("<Configure>",lambda event:halt_status.configure(wraplength=max(160,event.width-12)),add="+")

    engage_button = ttk.Button(home_actions, text="Engage", command=engage)
    engage_button.pack(side="left")
    ttk.Button(home_actions, text="View latest brief", command=open_brief).pack(side="left", padx=5)
    try:
        previous = read_brief()
        review.display(previous)
        latest_brief = previous
        refresh()
        cycle_status.configure(text=("Last cycle · " + summarize(previous)) if previous else "Ready for the first search.")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        latest_brief = None
        review.display(None, error="Select Engage to rebuild the latest brief from the lead archive.")
        cycle_status.configure(text="Select Engage to rebuild the latest brief.")
    refresh_accounts = install_accounts(accounts, directory, account_task, busy, webbrowser.open)
    heading(research, "Find opportunities")
    find_actions = action_row(research)
    ttk.Button(find_actions, text="Explore sources", command=revenue_workspace).pack(side="left")
    ttk.Button(find_actions, text="Plan a search", command=discovery_window).pack(side="left", padx=5)
    heading(research, "Review saved leads")
    lead_actions = action_row(research)
    ttk.Button(lead_actions, text="Browse leads", command=browse_leads).pack(side="left")
    ttk.Button(lead_actions, text="Compare leads", command=ranked_matrix).pack(side="left", padx=5)
    heading(research, "Work from a file")
    file_actions = action_row(research)
    importer = ttk.Button(file_actions, text="Import opportunities", command=import_file)
    importer.pack(side="left")
    simulator = ttk.Button(file_actions, text="Evaluate a scenario", command=import_scenario)
    simulator.pack(side="left", padx=5)

    ttk.Button(report_actions, text="Opportunity archive", command=browse_archive).pack(side="left")
    exporter = ttk.Button(report_actions, text="Export latest report", command=export_scenario, state="disabled")
    exporter.pack(side="left", padx=5)

    heading(settings, "Advanced preferences")
    resume_button.pack(anchor="w", pady=(0,4))
    ttk.Button(settings, text="Search settings", command=owner_profile_window).pack(anchor="w")
    heading(settings, "Appearance")
    ttk.Checkbutton(settings, text="Animate stars", variable=chrome.motion).pack(anchor="w")
    heading(settings, "Recovery")
    ttk.Button(settings, text="Recover interrupted Council attempts", command=recover_council).pack(anchor="w")
    ttk.Button(settings, text="Recover interrupted advisory attempts", command=recover_advisory).pack(anchor="w")

    heading(help_page, "Getting started")
    for line in ("1. Choose Engage on Home. Search or filter the live list and select any task or finding for details.",
                 "2. Reports shows the same live activity, the latest cycle brief and individual file results.",
                 "3. Emergency halt stops scheduling. After closing and reopening the application, choose Engage to start again."):
        ttk.Label(help_page, text=line, wraplength=440, justify="left").pack(anchor="w", pady=2)
    ttk.Label(help_page, text="In Reports → Work files, open the inbox to add CSVs or flat JSON records with text values. Scout checks CSV columns and converts JSON to CSV. Select a file to see its result or what needs attention.", wraplength=490, justify="left").pack(anchor="w", pady=4)
    heading(help_page, "Check the local research tools")
    diagnostics = action_row(help_page)
    launch = ttk.Button(diagnostics, text="Run example", command=run)
    launch.pack(side="left")
    diagnostic_buttons=[]
    for fixture_id,label in (("procurement","Run procurement fixture"),("digital_services","Run digital services fixture")):
        button=ttk.Button(diagnostics,text=label,command=partial(browser_diagnostic,fixture_id))
        button.pack(side="left",padx=2)
        diagnostic_buttons.append(button)
    for button in (launch,importer,simulator,*diagnostic_buttons):
        button.configure(state="disabled")
    if gui_smoke:
        try:
            smoke_cockpit(root,halt_button)
        except BaseException:
            close()
            raise
        if not stop.is_set() or str(launch.cget("state"))!="disabled":
            raise RuntimeError("desktop did not start halted")
        from time import monotonic, sleep
        root.geometry("800x550")
        root.deiconify()
        for tab_name, page_widget in pages.items():
            tabs.select(page_widget)
            root.update_idletasks()
            if (tabs.tab(tabs.select(), "text") != tab_name or not halt_button.winfo_ismapped()
                    or halt_button.winfo_rooty() >= page_widget.winfo_rooty() or not stop.is_set()):
                raise RuntimeError("Tab navigation lost the global halt control or changed runtime state")
        tabs.select(home)
        if os.name == "nt":
            from nexus_exchange.account_vault import AccountVault
            native = AccountVault(directory)
            native.save("sam", {"key": "synthetic-gui-check"})
            if native.load("sam") != {"key": "synthetic-gui-check"}:
                raise RuntimeError("Packaged Windows credential protection round trip failed")
            native.forget("sam")
        work_folder(directory, INBOX).joinpath("demo.json").write_text('[{"name":"Scout"}]', encoding="utf-8")
        work_folder(directory, INBOX).joinpath("fix.csv").write_text("id\n=formula\n", encoding="utf-8")
        from threading import Event
        release_search = Event()
        engage_button.invoke()
        deadline = monotonic() + 8
        try:
            while monotonic() < deadline:
                root.update()
                if any(row[1:3] == ("Engaged", "UK Find a Tender") for row in home_live.visible.values()):
                    break
                sleep(0.01)
            if (not home_live.visible or not any(row[1] == "Engaged" for row in home_live.visible.values())
                    or not any(row[1:3] == ("Pending", "CanadaBuys") for row in review.activity.visible.values())
                    or future is None or future.done()):
                raise RuntimeError("Both live views must show work before the source returns")
        finally:
            release_search.set()
        deadline = monotonic() + 20
        while future is not None and monotonic() < deadline:
            root.update()
            sleep(0.01)
        brief = read_brief()
        if future is not None or not engaged or not brief or len(brief["sources"]) != 2 or timer is None:
            raise RuntimeError("One-click first-run engagement did not compile and schedule the next search")
        open_brief()
        if tabs.select() != str(reports) or review.tabs.select() != str(review.summary):
            raise RuntimeError("Home did not open the full-window report")
        review.tabs.select(review.files)
        root.update_idletasks()
        if (not review.listing.winfo_ismapped() or len(review.items) != 2
                or "fix.csv" not in review.detail.cget("text") or brief["jobs"]["produced"] != 1):
            raise RuntimeError("Work files did not show the completed and held inbox jobs")
        tabs.select(home)
        halt_button.invoke()
        if timer is not None or engaged or not stop.is_set():
            raise RuntimeError("Emergency halt did not cancel recurring engagement")
        resume_button.invoke()
        if stop.is_set() or str(launch.cget("state"))!="normal":
            raise RuntimeError("explicit offline resume failed")
        launch.invoke()
        deadline = monotonic() + 20
        while future is not None:
            if monotonic() >= deadline:
                raise RuntimeError("Home example did not finish")
            root.update()
            sleep(0.01)
        if not result_panel.winfo_ismapped() or not output.get("1.0", "end").strip():
            raise RuntimeError("Home did not show the example result")
        tabs.select(reports)
        review.tabs.select(review.live_page)
        refresh()
        review.activity.query.set("OFFLINE SCREENING")
        if len(review.activity.visible) != 1 or next(iter(review.activity.visible.values()))[1] != "Completed":
            raise RuntimeError("Live report did not show the completed manual task")
        home_live.query.set("fix.csv")
        if len(home_live.visible) != 1 or next(iter(home_live.visible.values()))[1] != "Needs attention":
            raise RuntimeError("Home live search did not retain a held file")
        review.activity.query.set("no such event")
        if review.activity.visible or not home_live.visible:
            raise RuntimeError("Live activity filters leaked across tabs")
        home_live.query.set("")
        review.activity.query.set("")
        halt()
        if not stop.is_set() or str(launch.cget("state"))!="disabled":
            raise RuntimeError("desktop emergency halt failed")
        resume()
        if stop.is_set():
            raise RuntimeError("desktop smoke resume failed")
        if any(str(button.cget("state"))!="normal" for button in diagnostic_buttons):
            raise RuntimeError("Scout diagnostic did not enable after resume")
        root.withdraw()
        def wait_for_diagnostic():
            deadline=monotonic()+20
            while stop.browser_process_pending():
                if monotonic()>=deadline:
                    raise RuntimeError("Scout GUI diagnostic did not drain")
                root.update()
                sleep(0.01)
            root.update()
        for fixture_id in ("procurement","digital_services"):
            if not browser_diagnostic(fixture_id) or not stop.browser_process_pending():
                raise RuntimeError("Scout native process did not reserve")
            if not council_blocked() or any(str(button.cget("state"))!="disabled"
                                          for button in diagnostic_buttons):
                raise RuntimeError("Scout concurrent controls not blocked")
            wait_for_diagnostic()
            shown=output.get("1.0","end")
            report=json.loads(shown.split("\n",1)[1])
            if (report["fixture_id"]!=fixture_id or not report["child_process_completed"]
                    or report["worker_pid"]==os.getpid() or report["network_enabled"]
                    or report["fixture_report"]["attempts"]!=2):
                raise RuntimeError("Scout native process smoke failed")
        if not browser_diagnostic("procurement"):
            raise RuntimeError("Scout cancellation fixture did not reserve")
        halt()
        resume()
        if not stop.is_set() or not stop.browser_process_pending():
            raise RuntimeError("Scout halt did not block resume before drain")
        wait_for_diagnostic()
        if (any(str(button.cget("state"))!="disabled" for button in diagnostic_buttons)
                or browser_diagnostic("procurement")
                or output.get("1.0","end").strip()):
            raise RuntimeError("Scout diagnostic halt suppression failed")
        resume()
        window = browse_archive()
        if window.winfo_toplevel() != root or review.tabs.select() != str(window):
            raise RuntimeError("Opportunity archive must open inside Reports")
        leads_window = browse_leads()
        profile_window = owner_profile_window()
        pathway_window = revenue_workspace()
        trade_window = trade_catalog()
        routes_window = trade_routes_window()
        sample_id = "0"*32
        sample_lead = dict(notice_id=sample_id,title="Synthetic GUI fixture",deadline=None,
            source_url=notice_url(sample_id),research_candidate=False,
            blockers=["SYNTHETIC_FIXTURE"],todo=[dict(instruction=text) for _,text in CHECKS])
        ted_sample=dict(sample_lead,notice_id="1-2026",source_url=ted_notice_url("1-2026"),
            earliest_deadline_date="2026-12-03",title="Synthetic TED fixture")
        ted_window=show_source_results(dict(format="nexus-ted-research-v1",returned=1,
            requests=0,leads=[ted_sample],truncated=False))
        fts_sample=dict(sample_lead,notice_id="000001-2026",source_url=fts_notice_url("000001-2026"),
            title="Synthetic UK FTS fixture")
        fts_window=show_source_results(dict(format="nexus-fts-research-v1",returned=1,
            requests=0,leads=[fts_sample],truncated=False))
        canada_sample=dict(sample_lead,notice_id="cb-1",source_url=canada_notice_url("cb-1"),
            title="Synthetic CanadaBuys fixture",earliest_deadline_date="2026-12-01")
        canada_window=show_source_results(dict(format="nexus-canada-research-v1",returned=1,
            requests=0,leads=[canada_sample],truncated=False))
        spending_sample=dict(sample_lead,notice_id="CONT_AWD_SYNTHETIC_9700_-NONE-_-NONE-",
            source_url=award_url("CONT_AWD_SYNTHETIC_9700_-NONE-_-NONE-"),title="Synthetic prime award")
        spending_window=show_source_results(dict(format="nexus-usaspending-research-v1",returned=1,
            requests=0,leads=[spending_sample],truncated=False))
        # Populate a synthetic local history row for the checklist smoke.
        stamp=datetime.now(timezone.utc)
        todo_fixture=dict(sample_lead,retrieved_at=stamp.isoformat(),execution_eligible=False,
            external_authority=False,cash_exposure=None,
            blockers=["SYNTHETIC_FIXTURE","CASH_EXPOSURE_UNKNOWN","OWNER_APPROVAL_REQUIRED"])
        saved_report = dict(format="nexus-sam-research-v1", returned=1, requests=1, leads=[todo_fixture],
                            truncated=False, page_sha256=["0"*64])
        with LeadStore(directory / "scout-leads.sqlite3") as fixture_store:
            fixture_store.record(saved_report, now=stamp, halted=False)
            todo_row=fixture_store.browse(now=stamp,source="sam",halted=False)["leads"][0]
        todo_window=checklist_window(todo_row,root,smoke=True)
        # Use the first-run workflow to set up the profile needed by the receipt smoke.
        def descendants(parent):
            for child in parent.winfo_children():
                yield child
                yield from descendants(child)

        def control(parent, kind, label):
            return next(widget for widget in descendants(parent)
                        if isinstance(widget, kind) and widget.cget("text") == label)

        run(lambda *, halted: saved_report, target="Synthetic search result", scenario=True)
        deadline = monotonic() + 20
        while future is not None:
            if monotonic() >= deadline:
                raise RuntimeError("Synthetic result did not reach Home")
            root.update()
            sleep(0.01)
        if latest_results_window is None or latest_results_window.winfo_toplevel() != root:
            raise RuntimeError("Home did not retain the completed search results")
        tabs.select(home)
        recorded = store.read()
        select_result()
        results_window = latest_results_window
        if not results_window.winfo_exists() or store.read() != recorded or busy():
            raise RuntimeError("Reopening search results must reuse the completed report")
        control(results_window, ttk.Button, "Review checklist").invoke()
        reopened = results_window.nametowidget("checklist")
        if reopened.winfo_toplevel() != root:
            raise RuntimeError("Checklist opened outside the main window")
        review_tasks = next(widget for widget in descendants(reopened) if isinstance(widget, ttk.Treeview))
        if not any(review_tasks.set(item, "state") == "Evidence noted" for item in review_tasks.get_children()):
            raise RuntimeError("Search result failed to reopen its saved checklist notes")
        control(reopened, ttk.Button, "Back to notices").invoke()
        empty_window = show_source_results(dict(saved_report, returned=0, leads=[]))
        if not control(empty_window, ttk.Button, "Review checklist").instate(["disabled"]):
            raise RuntimeError("Empty search result enabled checklist review")
        empty_window.destroy()

        setup = discovery_window()
        start_search = control(setup, ttk.Button, "Search selected plan")
        if not start_search.instate(["disabled"]):
            raise RuntimeError("A fresh planner must wait for search settings")
        control(setup, ttk.Button, "Search settings").invoke()
        editor = next(widget for widget in setup.winfo_children() if isinstance(widget, tk.Toplevel))
        hours = next(widget for widget in descendants(editor) if widget.winfo_name() == "hours")
        hours.delete(0, "end")
        hours.insert(0, "20")
        control(editor, ttk.Checkbutton, "SAM.gov").invoke()
        control(editor, ttk.Button, "Save and return").invoke()
        declared = load_profile(directory, halt_check=stop.is_set)
        if (editor.winfo_exists() or start_search.instate(["disabled"])
                or declared["sources"] != ["sam"] or declared["hours_per_week"] != 20 or busy()):
            raise RuntimeError("Saving search settings must return to a ready, idle planner")
        setup.destroy()
        # Bind the existing owned synthetic observation to an exact search receipt.
        # No provider call, key, or additional observation is needed.
        from nexus_exchange.scout_discovery import build_plan
        from nexus_exchange.operator_capabilities import CSV_ID
        fixture_plan=build_plan(declared,CSV_ID,now=stamp,halted=False)
        fixture_option=next(row for row in fixture_plan["options"] if row["procurement_type"]=="k")
        _,fixture_query=resolve_query(fixture_plan,fixture_option["option_id"],declared,now=stamp,halted=False)
        with LeadStore(directory/"scout-leads.sqlite3") as fixture_store:
            inserted=fixture_store.record(dict(format="nexus-sam-research-v1",returned=1,
                leads=[todo_fixture],truncated=False,page_sha256=["0"*64],
                query=fixture_query.parameters(stamp),requests=1),now=stamp,halted=False,
                discovery=dict(plan=fixture_plan,option_id=fixture_option["option_id"],
                               profile=declared,started_at=stamp,task_id=uuid4().hex))
            if inserted!=0:
                raise RuntimeError("Synthetic receipt duplicated an existing observation")
        discovery=discovery_window(smoke=True)
        discovery.destroy()
        with LeadStore(directory / "scout-leads.sqlite3") as fixture_store:
            scenario_row=fixture_store.browse(now=datetime.now(timezone.utc),source="sam",profile=declared,halted=False)["leads"][0]
        scenario_window=open_scenario_window(root,scenario_row,directory=directory,halt_check=stop.is_set,
            council_action=council_action,council_blocked=council_blocked,
            operator_action=operator_action,operator_blocked=council_blocked,csv_action=csv_action,smoke=True)
        ranking_window=open_ranking_window(root,directory=directory,halt_check=stop.is_set,
            review_tasks=checklist_window,council_action=council_action,council_blocked=council_blocked,
            operator_action=operator_action,operator_blocked=council_blocked,csv_action=csv_action,smoke=True)
        # Synthetic saved-plan Council review and owner-drained recovery.
        from nexus_exchange.scenario_store import ScenarioStore
        from nexus_exchange.council_attempts import CouncilAttemptStore
        from nexus_exchange.scenario_council import ScenarioCouncil
        from nexus_exchange.council_coordinator import _prepare
        with ScenarioStore(directory/"scout-leads.sqlite3") as fixture_plans:
            saved=fixture_plans.list(context_for(scenario_row),halted=False)
            key=saved[0]["plan_id"]
        reviewed=council_action("history",key)
        if (reviewed["attempts_used"]!=1 or reviewed["external_authority"]
                or reviewed["attempts"][0]["audit_state"]!="RECORDED"):
            raise RuntimeError("Council runtime review smoke failed")
        # Reserve a second synthetic attempt, but do not dispatch it.
        fixture_council=ScenarioCouncil(directory,halt_check=stop.is_set)
        with fixture_council._snapshot(key) as (_snapshot,task,_artifacts):
            handoff,_=_prepare(task,2)
            with CouncilAttemptStore(directory/"council.sqlite3") as fixture_ledger:
                fixture_ledger.reserve(handoff,now=datetime.now(timezone.utc),halted=False)
        halt()
        resume()
        if not stop.is_set():
            raise RuntimeError("Council reservation did not block resume")
        recovered=recover_council()
        if recovered!=dict(recovered=1,escalated=0) or not stop.is_set():
            raise RuntimeError("Council recovery did not preserve halt")
        resume()
        if stop.is_set():
            raise RuntimeError("Council explicit resume failed")
        history=stop.council_action("history",key)
        if [item["audit_state"] for item in history["attempts"]]!=["RECORDED","INTERRUPTED_NO_REPORT"]:
            raise RuntimeError("Council recovery lost historical audit")
        # Owned fixture only: reserve reference metadata, not a model call.
        from nexus_exchange.advisory_attempts import AdvisoryAttemptStore, DB_NAME
        advisory_snapshot=stop.council_action("inspect",key)
        with AdvisoryAttemptStore(directory/DB_NAME) as advisory_store:
            advisory_store.reserve(advisory_snapshot,"d"*64,now=datetime.now(timezone.utc),
                                   approved=True,halted=stop.is_set())
        halt()
        resume()
        if not stop.is_set():
            raise RuntimeError("Advisory reservation did not block resume")
        recovered=recover_advisory()
        if recovered!=dict(recovered=1,escalated=0) or not stop.is_set():
            raise RuntimeError("Advisory recovery did not preserve halt")
        resume()
        if stop.is_set():
            raise RuntimeError("Advisory explicit resume failed")
        with AdvisoryAttemptStore(directory/DB_NAME,existing_only=True) as advisory_store:
            if advisory_store.status(key,halted=False)["state"]!="INTERRUPTED":
                raise RuntimeError("Advisory reservation replay or recovery mismatch")
        # Run only an owned deterministic child in the GUI/frozen smoke.
        # This does not dispatch a real model or consume a saved-plan attempt.
        from nexus_exchange.advisory_process import run_advisory_fixture
        advisory_fixture=run_advisory_fixture(stop.council_action("inspect",key),
                                             approved=True,halt_check=stop.is_set)
        if (advisory_fixture["worker_pid"]==os.getpid()
                or advisory_fixture["child_process_completed"] is not True
                or advisory_fixture["review"]["source_hold"] is None
                or advisory_fixture["model_executed"] is not False
                or advisory_fixture["external_authority"] is not False):
            raise RuntimeError("Advisory child fixture scope or lifecycle mismatch")
        # Separate synthetic research-candidate fixture: keep earlier source-held
        # scenario and ranking smoke unchanged. Never query a live source.
        operator_stamp=datetime.now(timezone.utc)
        operator_notice="1"*32
        operator_fixture=dict(todo_fixture,notice_id=operator_notice,
            source_url=notice_url(operator_notice),title="Synthetic RFQ opportunity",
            retrieved_at=operator_stamp.isoformat(),
            deadline=(operator_stamp+timedelta(days=7)).isoformat(),
            research_candidate=True,blockers=["CASH_EXPOSURE_UNKNOWN","OWNER_APPROVAL_REQUIRED"])
        with ScenarioStore(directory/"scout-leads.sqlite3") as fixture_plans:
            fixture_plans.record(dict(format="nexus-sam-research-v1",returned=1,
                leads=[operator_fixture],truncated=False,page_sha256=["1"*64]),
                now=operator_stamp,halted=False)
            operator_row=next(row for row in fixture_plans.browse(now=operator_stamp,
                source="sam",profile=declared,halted=False)["leads"] if row["notice_id"]==operator_notice)
            operator_key=fixture_plans.save(context_for(operator_row),saved[0]["scenario"],
                saved[0]["plan"],profile=declared,now=operator_stamp,halted=False)
        operator_window=open_operator_window(root,plan_id=operator_key,action=operator_action,
            blocked_check=council_blocked,smoke=True)
        operator_window.destroy()
        csv_source=directory/"synthetic-csv-input.csv"
        csv_destination=directory/"synthetic-csv-output.csv"
        csv_source.write_bytes(b"name,id\nBeta,002\nAlpha,001\n")
        csv_evidence=directory/"synthetic-obligation-evidence.txt"
        csv_evidence.write_bytes(b"Owned synthetic evidence fixture; no real customer acceptance.")
        try:
            from hashlib import sha256
            from nexus_exchange.ranking_workspace import RankingWorkspace
            from nexus_exchange.scout_requirements_form import open_service_requirements_window
            owned=csv_source.read_bytes()
            expected_scoped=b'"id","name"\r\n"001","Alpha"\r\n"002","Beta"\r\n'
            scoped_window=open_service_requirements_window(root,
                RankingWorkspace(directory,halt_check=stop.is_set),context_for(operator_row),
                operator_row["title"],plan_id=operator_key,sample_action=csv_action,
                blocked_check=council_blocked,smoke_sample=(csv_source,len(owned),sha256(owned).hexdigest(),expected_scoped,
                    directory/"synthetic-scoped-output.csv"))
            scoped_window.destroy()
            csv_window=open_csv_window(root,plan_id=operator_key,action=csv_action,
                blocked_check=council_blocked,smoke_paths=(csv_source,csv_destination),smoke_evidence=csv_evidence)
            csv_window.destroy()
            json_source=directory/"synthetic-json-input.json"
            json_destination=directory/"synthetic-json-output.csv"
            json_source.write_bytes(b'[{"name":"Beta","id":"002"},{"id":"001","name":"Alpha"}]')
            json_window=open_csv_window(root,plan_id=operator_key,action=csv_action,
                blocked_check=council_blocked,source_format="UTF8_JSON_RECORDS",
                smoke_paths=(json_source,json_destination))
            json_window.destroy()
            if json_destination.read_bytes()!=csv_destination.read_bytes():
                raise RuntimeError("JSON conversion native output mismatch")
            profile_destination=directory/"synthetic-csv-profile.csv"
            profile_window=open_csv_window(root,plan_id=operator_key,action=csv_action,
                blocked_check=council_blocked,operation="COLUMN_PROFILE",
                smoke_paths=(csv_source,profile_destination))
            profile_window.destroy()
            expected_profile=(b'"column","row_count","empty_count","whitespace_only_count","nonblank_count","distinct_nonblank_count","min_chars","max_chars"\r\n'
                b'"id","2","0","0","2","2","3","3"\r\n"name","2","0","0","2","2","4","5"\r\n')
            if profile_destination.read_bytes()!=expected_profile:
                raise RuntimeError("CSV quality report native output mismatch")
            right_csv=directory/"synthetic-csv-right.csv"
            right_csv.write_bytes(b"id,name\n001,Alfa\n003,Gamma\n")
            reconcile_destination=directory/"synthetic-csv-reconciliation.csv"
            reconcile_window=open_csv_window(root,plan_id=operator_key,action=csv_action,
                blocked_check=council_blocked,operation="RECONCILE",
                smoke_paths=(csv_source,right_csv,reconcile_destination))
            reconcile_window.destroy()
            expected_reconciliation=(b'"record_key","status","changed_field_count","changed_name"\r\n'
                b'"001","CHANGED","1","YES"\r\n"002","LEFT_ONLY","0","NOT_COMPARED"\r\n"003","RIGHT_ONLY","0","NOT_COMPARED"\r\n')
            if reconcile_destination.read_bytes()!=expected_reconciliation:
                raise RuntimeError("CSV reconciliation native output mismatch")
        except BaseException:
            close()
            raise
        root.update_idletasks()
        root.update()
        ranking_window.destroy()
        scenario_window.destroy()
        todo_window.destroy()
        spending_window.destroy()
        profile_window.destroy()
        leads_window.destroy()
        canada_window.destroy()
        fts_window.destroy()
        ted_window.destroy()
        window.destroy()
        pathway_window.destroy()
        trade_window.destroy()
        routes_window.destroy()
        results_window.destroy()
        close()
        return
    root.mainloop()

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    if "--genesis-self-test" in sys.argv:
        from nexus_exchange.genesis_diagnostic import run_diagnostic
        diagnostic=run_diagnostic(confirmed=True)
        sys.exit(0 if diagnostic["mode"]=="OWNED_OFFLINE_FIXTURE_ONLY" and not diagnostic["external_authority"] else 1)
    if "--fixture-process-self-test" in sys.argv:
        from nexus_exchange.browser_process import run_isolated_fixture
        for fixture_id in ("procurement","digital_services"):
            result=run_isolated_fixture(fixture_id,halted=False)
            if (result["fixture_id"]!=fixture_id or result["worker_pid"]==os.getpid()
                    or not result["child_process_completed"]
                    or result["network_enabled"] or result["browser_executed"]):
                sys.exit(1)
        sys.exit(0)
    if "--gui-self-test" in sys.argv:
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            main(data_directory=directory,gui_smoke=True)
        sys.exit(0)
    if "--self-test" in sys.argv:
        import tkinter
        result=demo()
        sys.exit(0 if len(result)==1 and result[0].screening.eligible_for_review else 1)
    main()
