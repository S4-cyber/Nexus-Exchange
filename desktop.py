"""Windows desktop preview; no external operations."""
import sys
import os
import json
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
from functools import partial
from uuid import uuid4
from nexus_exchange.event_store import EventStore
from nexus_exchange.lead_store import LeadStore, SOURCES as LEAD_FORMATS
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
    store = EventStore(directory / "events.sqlite3")
    executor = ThreadPoolExecutor(max_workers=1)
    stop = Event()
    future = None
    scenario_report = None
    def close():
        stop.set()
        executor.shutdown(wait=True, cancel_futures=True)
        store.close()
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
        if stop.is_set() or future is not None:
            return
        launch.configure(state="disabled")
        importer.configure(state="disabled")
        simulator.configure(state="disabled")
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
    def halt():
        stop.set()
        launch.configure(state="disabled")
        importer.configure(state="disabled")
        simulator.configure(state="disabled")
        halt_status.configure(text="HALTED — new tasks blocked")
    def resume():
        if future is None:
            stop.clear()
            launch.configure(state="normal")
            importer.configure(state="normal")
            simulator.configure(state="normal")
            halt_status.configure(text="Offline ready")
    def import_file():
        if stop.is_set() or future is not None:
            return
        path = filedialog.askopenfilename(parent=root,filetypes=[("Compiled snapshot manifest","*.json")])
        if path:
            run(partial(evaluate_file,path),target="Local compiled snapshot import")
    def import_scenario():
        if stop.is_set() or future is not None:
            return
        path = filedialog.askopenfilename(parent=root,filetypes=[("Deal scenario JSON","*.json")])
        if path:
            run(partial(evaluate_scenario,path,directory / "archive.sqlite3"),
                target="Offline deal simulation",scenario=True)
    def export_scenario():
        if scenario_report is None:
            return
        path = filedialog.asksaveasfilename(parent=root,defaultextension=".json",
            filetypes=[("JSON","*.json")],initialfile="nexus-report.json")
        if path:
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
            if stop.is_set() or future is not None:
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
            if stop.is_set() or future is not None:
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
            if stop.is_set() or future is not None:
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
            if stop.is_set() or future is not None:
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
            if stop.is_set() or future is not None:
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
    def browse_leads():
        window=tk.Toplevel(root)
        window.title("Nexus Exchange | Unified Scout history")
        window.geometry("1050x720")
        ttk.Label(window,text="SCOUT — Historical lead memory",font=("Segoe UI",18)).pack(pady=8)
        ttk.Label(window,text="Saved observations only. Every lead requires current verification.").pack()
        filters=ttk.Frame(window)
        filters.pack(fill="x",padx=12,pady=8)
        source=tk.StringVar(value="All")
        search=tk.StringVar(value="")
        ttk.Combobox(filters,textvariable=source,values=["All","sam","ted","uk_tender","canada","usaspending"],
            state="readonly",width=18).pack(side="left",padx=5)
        ttk.Entry(filters,textvariable=search,width=40).pack(side="left",padx=5)
        summary=ttk.Label(window)
        summary.pack()
        tree=ttk.Treeview(window,columns=("source","title","retrieved","deadline"),show="headings",height=10)
        for col,label,width in (("source","Source",105),("title","Notice",420),
                ("retrieved","Retrieved UTC",205),("deadline","Reported deadline",210)):
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
                    "Verification blockers: "+", ".join(row["blockers"]),"","TO DO",
                    *("[ ] "+t["instruction"] for t in row["todo"])]))
        def reload():
            nonlocal report
            report=None
            rows.clear()
            for item in tree.get_children():
                tree.delete(item)
            try:
                with LeadStore(directory / "scout-leads.sqlite3") as store:
                    report=store.browse(now=datetime.now(timezone.utc),
                        source=None if source.get()=="All" else source.get(),
                        query=search.get(),halted=stop.is_set())
                for i,row in enumerate(report["leads"]):
                    rows[str(i)]=row
                    tree.insert("","end",iid=str(i),values=(row["source"],row["title"],
                        row["retrieved_at"],row["deadline"] or row["earliest_deadline_date"] or "Unverified"))
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
            if path:
                try:
                    export_report(path,report)
                except OSError as exc:
                    messagebox.showerror("Export failed",type(exc).__name__,parent=window)
        ttk.Button(filters,text="Filter / refresh",command=reload).pack(side="left",padx=5)
        buttons=ttk.Frame(window)
        buttons.pack(pady=6)
        ttk.Button(buttons,text="Open official notice",command=open_selected).pack(side="left")
        ttk.Button(buttons,text="Export history JSON",command=export).pack(side="left",padx=5)
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
            if report is None:
                return
            path = filedialog.asksaveasfilename(parent=window,defaultextension=".json",
                filetypes=[("JSON","*.json")],initialfile="nexus-exchange-archive.json")
            if path:
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
    halt_status = ttk.Label(root,text="Offline ready")
    halt_status.pack()
    if gui_smoke:
        window = browse_archive()
        leads_window = browse_leads()
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
        root.update_idletasks()
        root.update()
        spending_window.destroy()
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
