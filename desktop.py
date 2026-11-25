"""Windows desktop preview; no external operations."""
import sys
import os
import json
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from functools import partial
from uuid import uuid4
from nexus_exchange.event_store import EventStore
from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.lead_store import LeadStore, SOURCES as LEAD_FORMATS
from nexus_exchange.owner_profile import ProfileStore, PROFILE_SOURCES
from nexus_exchange.checklist_store import ChecklistStore, context_for
from nexus_exchange.scenario_workspace import open_scenario_window
from nexus_exchange.operator_workspace import open_operator_window
from nexus_exchange.ranking_workspace import open_ranking_window
from nexus_exchange.evidence import fingerprint, verify_reference, EvidenceError
from nexus_exchange.opportunity_archive import OpportunityArchive
from nexus_exchange.dashboard_events import project
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

def run_logged(store, stop=None, archive=None, *, work=None, target="Offline screening", lead_store=None):
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
        result = (demo if work is None else work)(halted=stop.is_set() if stop is not None else False)
        if stop is not None and stop.is_set():
            record("cancelled")
            return ()
        if archive is not None:
            archive.record(tuple(item.observation for item in result))
        if lead_store is not None and type(result) is dict and result.get("format") in LEAD_FORMATS:
            lead_store.record(result,now=datetime.now(timezone.utc),halted=stop.is_set() if stop is not None else False)
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
    root = tk.Tk()
    root.title("Nexus Exchange | Offline preview")
    root.geometry("1080x820")
    directory = Path(data_directory) if data_directory is not None else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NexusExchange"
    if gui_smoke:
        root.withdraw()
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
    scenario_report = None
    def busy():
        return future is not None or stop.browser_process_pending()
    def close():
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
    ttk.Label(root,text="NEXUS EXCHANGE",font=("Segoe UI",24)).pack(pady=20)
    ttk.Label(root,text="RESEARCH PREVIEW — Commercial actions disabled").pack()
    tasks = ttk.LabelFrame(root,text="Active tasks")
    tasks.pack(fill="x",padx=20,pady=8)
    slots = []
    for i in range(10):
        cell = ttk.Label(tasks,text="Idle",width=24,anchor="center",relief="groove")
        cell.grid(row=i//5,column=i%5,sticky="ew",padx=3,pady=4)
        tasks.columnconfigure(i%5,weight=1)
        slots.append(cell)
    history = ttk.Treeview(root,columns=("time","target","state"),show="headings",height=7)
    for key,label in (("time","UTC timestamp"),("target","Target"),("state","Status")):
        history.heading(key,text=label)
        history.column(key,width=220 if key=="time" else 160)
    history.pack(fill="both",padx=20,pady=8)
    output = ScrolledText(root,height=8,wrap="word")
    output.pack(fill="both",expand=True,padx=20,pady=16)
    output.configure(state="disabled")
    status = ttk.Label(root)
    status.pack()
    page = 1
    def refresh():
        nonlocal page
        events = store.read()
        first = project(events)
        page = min(page,first["pages"])
        view = project(events,page)
        for i,slot in enumerate(slots):
            slot.configure(text=(view["tasks"][i].target+" | "+view["tasks"][i].state) if i<len(view["tasks"]) else "Idle")
        page_label.configure(text=f"Page {page} / {view['pages']}")
        for item in history.get_children():
            history.delete(item)
        for event in reversed(view["history"][-100:]):
            history.insert("","end",values=(event.timestamp,event.target,event.state))
        status.configure(text=f"Successful tasks: {view['successful_tasks']} | Recorded events: {len(view['history'])}")
    navigation = ttk.Frame(root)
    navigation.pack()
    def move(delta):
        nonlocal page
        page = max(1,min(page+delta,project(store.read())["pages"]))
        refresh()
    ttk.Button(navigation,text="Previous",command=lambda:move(-1)).pack(side="left")
    page_label = ttk.Label(navigation)
    page_label.pack(side="left",padx=8)
    ttk.Button(navigation,text="Next",command=lambda:move(1)).pack(side="left")
    refresh()
    def worker(work=None, target="Offline screening", scenario=False):
        local = EventStore(directory / "events.sqlite3")
        try:
            if scenario:
                with LeadStore(directory / "scout-leads.sqlite3") as leads:
                    return run_logged(local, stop, work=work, target=target, lead_store=leads)
            with OpportunityArchive(directory / "archive.sqlite3") as archive:
                return run_logged(local, stop, archive, work=work, target=target)
        finally:
            local.close()
    def run(work=None, target="Offline screening", scenario=False):
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
        future = executor.submit(worker, work, target, scenario)
        poll()
    def poll():
        nonlocal future, scenario_report
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
                    output.insert("end",f"Scout discovery: {result['returned']} records; {result['requests']} requests.\nResearch only; no execution eligibility.\nSee the results window or export the full report.")
                    show_source_results(result)
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
        nonlocal scenario_report
        scenario_report=None
        exporter.configure(state="disabled")
        output.configure(state="normal")
        output.delete("1.0","end")
        output.configure(state="disabled")
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
    def browser_diagnostic(fixture_id):
        nonlocal scenario_report
        if council_blocked():
            return False
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
        halt_status.configure(text="Scout diagnostic running — Emergency halt available.")
        root.after(25,browser_poll)
        return True
    def browser_poll():
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
            if not stop.is_set():
                try:
                    stop.set()
                except Exception:
                    pass
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
    def show_source_results(report):
        window = tk.Toplevel(root)
        source_format=report.get("format","nexus-sam-research-v1")
        label,link_for={
            "nexus-sam-research-v1":("SAM",notice_url),
            "nexus-ted-research-v1":("TED",ted_notice_url),
            "nexus-fts-research-v1":("UK Find a Tender",fts_notice_url),
            "nexus-canada-research-v1":("CanadaBuys",canada_notice_url),
            "nexus-usaspending-research-v1":("USAspending award intelligence",award_url),
        }[source_format]
        window.title("Nexus Exchange | "+label+" research leads")
        window.geometry("1050x700")
        count = sum(lead["research_candidate"] for lead in report["leads"])
        ttk.Label(window,text=f"{report['returned']} notices | {count} research candidates | {report['requests']} requests").pack(pady=6)
        ttk.Label(window,text="No lead is approved for execution. Unknown cash exposure blocks Genesis.",wraplength=1000).pack()
        if report.get("truncated"):
            ttk.Label(window,text="Search capped by request budget; additional notices not retrieved.").pack()
        if source_format=="nexus-usaspending-research-v1":
            ttk.Label(window,text="Historical prime awards, NOT open subcontracting offers. Verify actual demand.").pack()
        if source_format=="nexus-canada-research-v1":
            ttk.Label(window,text="Daily dataset snapshot; verify the original tender and exact closing timezone.").pack()
        if source_format=="nexus-fts-research-v1":
            ttk.Label(window,text="Historical releases only. The complete procurement lifecycle is not compiled.").pack()
        tree=ttk.Treeview(window,columns=("title","deadline","state"),show="headings",height=8)
        for col,label,width in (("title","Opportunity",510),("deadline","Deadline / reported date",200),("state","Research status",170)):
            tree.heading(col,text=label)
            tree.column(col,width=width,anchor="w")
        tree.pack(fill="x",padx=12,pady=8)
        leads={lead["notice_id"]:lead for lead in report["leads"]}
        for key,lead in leads.items():
            tree.insert("","end",iid=key,values=(lead["title"],lead["deadline"] or lead.get("earliest_deadline_date") or "Unverified",
                "Award intelligence" if source_format=="nexus-usaspending-research-v1" else "Review candidate" if lead["research_candidate"] else "Blocked"))
        details=ScrolledText(window,height=15,wrap="word",state="disabled")
        details.pack(fill="both",expand=True,padx=12,pady=8)
        def selected():
            selection=tree.selection()
            return leads.get(selection[0]) if selection else None
        def display(event=None):
            lead=selected()
            details.configure(state="normal")
            details.delete("1.0","end")
            if lead is not None:
                lines=[lead["title"],"Notice ID: "+lead["notice_id"],
                    "Source: "+lead["source_url"],"Blockers: "+", ".join(lead["blockers"]),
                    "", "TO DO — evidence required"]
                if "award_metadata" in lead:
                    lines[3:3]=[f"{k}: {v or 'Unknown'}" for k,v in lead["award_metadata"].items()]
                lines.extend("[ ] "+task["instruction"] for task in lead["todo"])
                details.insert("end","\n".join(lines))
            details.configure(state="disabled")
        def open_notice():
            lead=selected()
            if lead is not None and not stop.is_set():
                try:
                    webbrowser.open(link_for(lead["notice_id"]),new=2)
                except (ValueError,OSError):
                    messagebox.showerror("Browser unavailable","Unable to open official notice.",parent=window)
        tree.bind("<<TreeviewSelect>>",display)
        ttk.Button(window,text="Open selected official notice",command=open_notice).pack(pady=8)
        if leads:
            tree.selection_set(next(iter(leads)))
            display()
        return window
    def trade_routes_window():
        window=tk.Toplevel(root)
        window.title("Nexus Exchange | Commercial routes")
        window.geometry("1050x700")
        ttk.Label(window,text="Commercial routes — research and compliance only",font=("Segoe UI",16)).pack(pady=8)
        ttk.Label(window,text="No route grants authority or establishes zero cash exposure.").pack()
        tree=ttk.Treeview(window,columns=("route","model","capital","gate"),show="headings",height=12)
        for key,label,width in (("route","Commercial route",300),("model","Revenue model",265),("capital","Capital status",145),("gate","Review gate",160)):
            tree.heading(key,text=label)
            tree.column(key,width=width,anchor="w")
        tree.pack(fill="x",padx=12,pady=8)
        view=ScrolledText(window,height=10,wrap="word",state="disabled")
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
        window = tk.Toplevel(root)
        window.title("Nexus Exchange | Scout global trade catalog")
        window.geometry("1050x760")
        ttk.Label(window,text="SCOUT — Global trade sources",font=("Segoe UI",18)).pack(pady=8)
        ttk.Label(window,text="Documented sources, not connected accounts or verified revenue. SAM pilot is separate.").pack()
        filters=ttk.Frame(window)
        filters.pack(fill="x",padx=12,pady=8)
        kind=tk.StringVar(value="All")
        query=tk.StringVar(value="")
        ttk.Label(filters,text="Income type").pack(side="left")
        ttk.Combobox(filters,textvariable=kind,values=["All",*KINDS],state="readonly",width=18).pack(side="left",padx=6)
        ttk.Entry(filters,textvariable=query,width=40).pack(side="left",padx=6)
        tree=ttk.Treeview(window,columns=("name","sector","access","priority"),show="headings",height=10)
        for col,label,width in (("name","Source",265),("sector","Market",210),
                ("access","Access pathway",170),("priority","Integration priority",120)):
            tree.heading(col,text=label)
            tree.column(col,width=width,anchor="w")
        tree.pack(fill="x",padx=12,pady=6)
        details=ScrolledText(window,height=15,wrap="word",state="disabled")
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
        ttk.Button(filters,text="Filter sources",command=reload).pack(side="left")
        buttons=ttk.Frame(window)
        buttons.pack(pady=8)
        ttk.Button(buttons,text="Open official source",command=open_selected).pack(side="left")
        ttk.Button(buttons,text="Open integration documentation",command=lambda:open_selected(True)).pack(side="left",padx=5)
        ttk.Button(buttons,text="Commercial routes",command=trade_routes_window).pack(side="left",padx=5)
        ttk.Button(buttons,text="Search EU TED (keyless)",command=run_ted).pack(side="left",padx=5)
        ttk.Button(buttons,text="Search UK FTS",command=run_fts).pack(side="left",padx=5)
        ttk.Button(buttons,text="Search CanadaBuys",command=run_canada).pack(side="left",padx=5)
        ttk.Button(buttons,text="Research USAspending",command=run_spending).pack(side="left",padx=5)
        tree.bind("<<TreeviewSelect>>",display)
        reload()
        return window
    def revenue_workspace():
        window = tk.Toplevel(root)
        window.title("Nexus Exchange | Scout revenue pathways")
        window.geometry("900x760")
        ttk.Label(window,text="SCOUT — Revenue pathways",font=("Segoe UI",18)).pack(pady=10)
        ttk.Label(window,text="Planning only. Budget entries do not connect a bank or authorize spending.").pack()
        settings = ttk.Frame(window)
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
        prerequisites = ttk.Label(window,wraplength=850,justify="left")
        prerequisites.pack(fill="x",padx=15,pady=6)
        flags={key:tk.BooleanVar(value=False) for key,_ in CHECKS}
        checklist=ttk.LabelFrame(window,text="To do — owner assertions only, independent verification required")
        checklist.pack(fill="x",padx=15,pady=8)
        for key,instruction in CHECKS:
            ttk.Checkbutton(checklist,text=instruction,variable=flags[key]).pack(anchor="w",padx=6,pady=3)
        result=ttk.Label(window,wraplength=850,justify="left")
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
        selector = ttk.Frame(window)
        selector.pack(fill="x",padx=15,pady=4)
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
        buttons=ttk.Frame(window)
        buttons.pack(pady=8)
        ttk.Button(buttons,text="Open official source",command=open_source).pack(side="left")
        ttk.Button(buttons,text="Search SAM (read only)",command=run_sam).pack(side="left")
        ttk.Button(buttons,text="Refresh checklist",command=refresh_plan).pack(side="left")
        ttk.Button(buttons,text="Global trade catalog",command=trade_catalog).pack(side="left")
        refresh_plan()
        return window
    def owner_profile_window():
        window=tk.Toplevel(root)
        window.title("Nexus Exchange | Owner capability profile")
        window.geometry("880x690")
        ttk.Label(window,text="OWNER — Declared research capabilities",font=("Segoe UI",18)).pack(pady=8)
        ttk.Label(window,text="Local planning only. No identity verification, credentials, bank details or authority.",wraplength=820).pack(pady=6)
        form=ttk.Frame(window)
        form.pack(fill="x",padx=20,pady=12)
        values={"mode":tk.StringVar(value="genesis"),"budget":tk.StringVar(value="0"),
            "hours_per_week":tk.StringVar(value="0"),"naics":tk.StringVar(value=""),
            "cpv":tk.StringVar(value=""),"keywords":tk.StringVar(value="")}
        fields=(("Operating pathway","mode"),("USD planning budget (not balance)","budget"),
            ("Declared weekly availability, hours","hours_per_week"),("NAICS six-digit codes, comma separated","naics"),
            ("CPV prefixes, comma separated","cpv"),("Service keywords, comma separated","keywords"))
        for i,(label,key) in enumerate(fields):
            ttk.Label(form,text=label).grid(row=i,column=0,sticky="w",pady=5)
            widget=(ttk.Combobox(form,textvariable=values[key],values=["genesis","catalyst"],state="readonly")
                if key=="mode" else ttk.Entry(form,textvariable=values[key],width=42))
            widget.grid(row=i,column=1,sticky="ew",padx=8)
        form.columnconfigure(1,weight=1)
        ttk.Label(window,text="Only declare services you can actually deliver. Examples: NAICS 541511, CPV 72, keyword software. No private or sensitive information.",wraplength=810).pack(padx=20,pady=8)
        source_box=ttk.LabelFrame(window,text="Sources to prioritize")
        source_box.pack(fill="x",padx=20,pady=8)
        flags={source:tk.BooleanVar(value=False) for source in PROFILE_SOURCES}
        for source,flag in flags.items():
            ttk.Checkbutton(source_box,text=source,variable=flag).pack(side="left",padx=7,pady=8)
        message=ttk.Label(window,wraplength=810)
        message.pack(fill="x",padx=20,pady=8)
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
        def load():
            try:
                with ProfileStore(directory / "owner-profile.sqlite3") as store:
                    profile=store.load(halted=stop.is_set())
                populate(profile)
                message.configure(text="Saved profile loaded." if profile else "No profile saved. Defaults grant no permissions.")
            except (ValueError,PermissionError,OSError):
                message.configure(text="Profile unavailable or research halted.")
        def save():
            if stop.is_set():
                message.configure(text="Research halted.")
                return
            try:
                profile=dict(mode=values["mode"].get(),budget=values["budget"].get(),
                    hours_per_week=int(values["hours_per_week"].get()),
                    naics=split("naics"),cpv=split("cpv"),keywords=[x.casefold() for x in split("keywords")],
                    sources=[s for s,v in flags.items() if v.get()])
                with ProfileStore(directory / "owner-profile.sqlite3") as store:
                    revision=store.save(profile,halted=stop.is_set())
                message.configure(text="Saved declared profile "+revision[:12]+". Refresh Scout history to apply priorities.")
            except (ValueError,PermissionError,OSError):
                message.configure(text="Invalid profile. Check codes, hours, budget and duplicate entries.")
        def clear():
            if stop.is_set():
                message.configure(text="Research halted.")
                return
            if messagebox.askyesno("Clear local profile","Remove saved planning preferences?",parent=window):
                with ProfileStore(directory / "owner-profile.sqlite3") as store:
                    store.clear(halted=stop.is_set())
                load()
        buttons=ttk.Frame(window)
        buttons.pack(pady=10)
        ttk.Button(buttons,text="Save local profile",command=save).pack(side="left",padx=6)
        ttk.Button(buttons,text="Reload",command=load).pack(side="left",padx=6)
        ttk.Button(buttons,text="Clear profile",command=clear).pack(side="left",padx=6)
        load()
        return window
    def checklist_window(row,parent,*,smoke=False):
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
        window=tk.Toplevel(parent)
        window.title("Nexus Exchange | Persistent To Do")
        window.geometry("1000x720")
        ttk.Label(window,text="TO DO — Owner review notes",font=("Segoe UI",18)).pack(pady=8)
        ttk.Label(window,text=row["title"],wraplength=940).pack(padx=12)
        ttk.Label(window,text="Evidence noted means an owner assertion, NOT verification or authorization.",
            wraplength=940).pack(pady=4)
        summary=ttk.Label(window)
        summary.pack()
        tree=ttk.Treeview(window,columns=("instruction","state"),show="headings",height=9)
        tree.heading("instruction",text="Required check")
        tree.heading("state",text="Owner review state")
        tree.column("instruction",width=730,anchor="w")
        tree.column("state",width=180,anchor="w")
        tree.pack(fill="x",padx=12,pady=8)
        instruction=ttk.Label(window,wraplength=940,justify="left")
        instruction.pack(fill="x",padx=12,pady=4)
        editor=ttk.Frame(window)
        editor.pack(fill="x",padx=12,pady=8)
        labels={"pending":"Pending","needs_followup":"Needs follow-up","evidence_noted":"Evidence noted"}
        values={v:k for k,v in labels.items()}
        state=tk.StringVar(value=labels["pending"])
        reference=tk.StringVar(value="")
        ttk.Label(editor,text="State").grid(row=0,column=0,sticky="w")
        ttk.Combobox(editor,textvariable=state,values=list(labels.values()),state="readonly",width=22).grid(row=0,column=1,sticky="w")
        ttk.Label(editor,text="Evidence reference (no credentials or personal data)").grid(row=1,column=0,sticky="w",pady=6)
        ttk.Entry(editor,textvariable=reference).grid(row=1,column=1,sticky="ew",padx=8)
        editor.columnconfigure(1,weight=1)
        message=ttk.Label(window,wraplength=940,justify="left")
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
        buttons=ttk.Frame(window)
        buttons.pack(pady=6)
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
            operator_action=operator_action,operator_blocked=council_blocked)
    def browse_leads():
        window=tk.Toplevel(root)
        window.title("Nexus Exchange | Unified Scout history")
        window.geometry("1050x720")
        ttk.Label(window,text="SCOUT — Historical lead memory",font=("Segoe UI",18)).pack(pady=8)
        ttk.Label(window,text="Saved observations only. Owner profile changes review order, never eligibility.").pack()
        filters=ttk.Frame(window)
        filters.pack(fill="x",padx=12,pady=8)
        source=tk.StringVar(value="All")
        search=tk.StringVar(value="")
        ttk.Combobox(filters,textvariable=source,values=["All","sam","ted","uk_tender","canada","usaspending"],
            state="readonly",width=18).pack(side="left",padx=5)
        ttk.Entry(filters,textvariable=search,width=40).pack(side="left",padx=5)
        summary=ttk.Label(window)
        summary.pack()
        tree=ttk.Treeview(window,columns=("source","title","fit","deadline"),show="headings",height=10)
        for col,label,width in (("source","Source",105),("title","Notice",420),
                ("fit","Review priority",235),("deadline","Reported deadline",175)):
            tree.heading(col,text=label)
            tree.column(col,width=width,anchor="w")
        tree.pack(fill="x",padx=12,pady=6)
        details=ScrolledText(window,height=15,wrap="word",state="disabled")
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
        buttons=ttk.Frame(window)
        buttons.pack(pady=6)
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
                        operator_action=operator_action,operator_blocked=council_blocked)
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
    def browse_archive():
        window = tk.Toplevel(root)
        window.title("Nexus Exchange | Historical opportunities")
        window.geometry("850x600")
        ttk.Label(window,text="Historical observations — newest 100, re-screened on refresh; not live offers").pack(pady=8)
        search = ttk.Entry(window)
        search.pack(fill="x",padx=12,pady=4)
        view = ScrolledText(window,wrap="word")
        view.pack(fill="both",expand=True,padx=12,pady=8)
        report = None
        def reload():
            nonlocal report
            try:
                if stop.is_set():
                    raise PermissionError("HALTED")
                report = archive_report(directory / "archive.sqlite3",
                    now=datetime.now(timezone.utc),query=search.get())
                value = json.dumps(report,ensure_ascii=True,indent=2)
            except Exception as exc:
                report = None
                value = "Archive unavailable: " + type(exc).__name__
            view.configure(state="normal")
            view.delete("1.0","end")
            view.insert("end",value)
            view.configure(state="disabled")
        def export():
            if report is None or stop.is_set():
                return
            path = filedialog.asksaveasfilename(parent=window,defaultextension=".json",
                filetypes=[("JSON","*.json")],initialfile="nexus-exchange-archive.json")
            if path and not stop.is_set() and report is not None:
                try:
                    export_report(path, report)
                except OSError as exc:
                    messagebox.showerror("Export failed",type(exc).__name__,parent=window)
        buttons = ttk.Frame(window)
        buttons.pack(pady=8)
        ttk.Button(buttons,text="Search / refresh",command=reload).pack(side="left")
        ttk.Button(buttons,text="Export displayed JSON",command=export).pack(side="left")
        reload()
        return window
    controls = ttk.Frame(root)
    controls.pack(pady=10)
    launch = ttk.Button(controls,text="Run offline demonstration",command=run)
    launch.pack(side="left")
    importer = ttk.Button(controls,text="Import compiled JSON",command=import_file)
    importer.pack(side="left")
    ttk.Button(controls,text="Emergency halt",command=halt).pack(side="left")
    ttk.Button(controls,text="Resume offline",command=resume).pack(side="left")
    ttk.Button(controls,text="Opportunity archive",command=browse_archive).pack(side="left")
    simulation_controls = ttk.Frame(root)
    simulation_controls.pack(pady=5)
    simulator = ttk.Button(simulation_controls,text="Evaluate deal scenario JSON",command=import_scenario)
    simulator.pack(side="left")
    exporter = ttk.Button(simulation_controls,text="Export report JSON",command=export_scenario,state="disabled")
    exporter.pack(side="left")
    ttk.Button(simulation_controls,text="Scout revenue pathways",command=revenue_workspace).pack(side="left")
    ttk.Button(simulation_controls,text="Scout lead history",command=browse_leads).pack(side="left")
    ttk.Button(simulation_controls,text="Ranked Matrix",command=ranked_matrix).pack(side="left")
    ttk.Button(simulation_controls,text="Owner profile",command=owner_profile_window).pack(side="left")
    diagnostics=ttk.LabelFrame(root,text="Scout browser diagnostics (offline synthetic fixtures)")
    diagnostics.pack(pady=4)
    diagnostic_buttons=[]
    for fixture_id,label in (("procurement","Run procurement fixture"),("digital_services","Run digital services fixture")):
        button=ttk.Button(diagnostics,text=label,command=partial(browser_diagnostic,fixture_id))
        button.pack(side="left",padx=4)
        diagnostic_buttons.append(button)
    ttk.Button(root,text="Recover interrupted Council attempts",command=recover_council).pack(pady=2)
    halt_status = ttk.Label(root,text=f"HALTED — {stop.recovered_count} journal tasks, "
        f"{stop.council_recovered_count} Council attempts reconciled; Resume offline to begin",wraplength=1040)
    halt_status.pack()
    for button in (launch,importer,simulator,*diagnostic_buttons):
        button.configure(state="disabled")
    if gui_smoke:
        if not stop.is_set() or str(launch.cget("state"))!="disabled":
            raise RuntimeError("desktop did not start halted")
        resume()
        if stop.is_set() or str(launch.cget("state"))!="normal":
            raise RuntimeError("explicit offline resume failed")
        halt()
        if not stop.is_set() or str(launch.cget("state"))!="disabled":
            raise RuntimeError("desktop emergency halt failed")
        resume()
        if stop.is_set():
            raise RuntimeError("desktop smoke resume failed")
        if any(str(button.cget("state"))!="normal" for button in diagnostic_buttons):
            raise RuntimeError("Scout diagnostic did not enable after resume")
        from time import monotonic,sleep
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
        leads_window = browse_leads()
        profile_window = owner_profile_window()
        pathway_window = revenue_workspace()
        trade_window = trade_catalog()
        routes_window = trade_routes_window()
        sample_id = "0"*32
        sample_lead = dict(notice_id=sample_id,title="Synthetic GUI fixture",deadline=None,
            source_url=notice_url(sample_id),research_candidate=False,
            blockers=["SYNTHETIC_FIXTURE"],todo=[dict(instruction=text) for _,text in CHECKS])
        results_window = show_source_results(dict(returned=1,requests=0,leads=[sample_lead],truncated=False))
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
        with LeadStore(directory / "scout-leads.sqlite3") as fixture_store:
            fixture_store.record(dict(format="nexus-sam-research-v1",returned=1,leads=[todo_fixture],
                truncated=False,page_sha256=["0"*64]),now=stamp,halted=False)
            todo_row=fixture_store.browse(now=stamp,source="sam",halted=False)["leads"][0]
        todo_window=checklist_window(todo_row,root,smoke=True)
        with ProfileStore(directory / "owner-profile.sqlite3") as fixture_profiles:
            declared=dict(mode="genesis",budget="0",hours_per_week=20,sources=["sam"],naics=[],cpv=[],keywords=[])
            fixture_profiles.save(declared,halted=False)
        with LeadStore(directory / "scout-leads.sqlite3") as fixture_store:
            scenario_row=fixture_store.browse(now=datetime.now(timezone.utc),source="sam",profile=declared,halted=False)["leads"][0]
        scenario_window=open_scenario_window(root,scenario_row,directory=directory,halt_check=stop.is_set,
            council_action=council_action,council_blocked=council_blocked,
            operator_action=operator_action,operator_blocked=council_blocked,smoke=True)
        ranking_window=open_ranking_window(root,directory=directory,halt_check=stop.is_set,
            review_tasks=checklist_window,council_action=council_action,council_blocked=council_blocked,
            operator_action=operator_action,operator_blocked=council_blocked,smoke=True)
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
