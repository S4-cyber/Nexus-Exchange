"""Windows desktop preview; no external operations."""
import sys
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
from uuid import uuid4
from nexus_exchange.event_store import EventStore
from nexus_exchange.dashboard_events import project
from datetime import datetime, timezone, timedelta
from nexus_exchange.pipeline import evaluate_snapshots

def demo(*, halted=False):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now.isoformat()
    release = dict(ocid="ocds-demo-1", id="demo-1", date=stamp,
        tender=dict(status="active", title="Synthetic procurement opportunity",
        tenderPeriod=dict(endDate=(now+timedelta(days=7)).isoformat()),
        value=dict(amount=1000,currency="USD")))
    return evaluate_snapshots("demo",[release],"https://example.org/demo",stamp,now=now,halted=halted)

def run_logged(store, stop=None):
    task = uuid4().hex
    def record(state):
        store.append(dict(task_id=task,target="Offline screening",state=state,
            timestamp=datetime.now(timezone.utc).isoformat()))
    record("queued")
    record("running")
    try:
        result = demo(halted=stop.is_set() if stop is not None else False)
        if stop is not None and stop.is_set():
            record("cancelled")
            return ()
    except Exception:
        record("failed")
        raise
    record("succeeded")
    return result

def main():
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("Nexus Exchange | Offline preview")
    root.geometry("980x760")
    directory = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NexusExchange"
    directory.mkdir(parents=True, exist_ok=True)
    store = EventStore(directory / "events.sqlite3")
    executor = ThreadPoolExecutor(max_workers=1)
    stop = Event()
    future = None
    def close():
        stop.set()
        executor.shutdown(wait=True, cancel_futures=True)
        store.close()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    ttk.Label(root,text="NEXUS EXCHANGE",font=("Segoe UI",24)).pack(pady=20)
    ttk.Label(root,text="OFFLINE DEMONSTRATION — External actions disabled").pack()
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
    output = tk.Text(root,height=8,wrap="word")
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
    def worker():
        local = EventStore(directory / "events.sqlite3")
        try:
            return run_logged(local, stop)
        finally:
            local.close()
    def run():
        nonlocal future
        if stop.is_set() or future is not None:
            return
        launch.configure(state="disabled")
        future = executor.submit(worker)
        poll()
    def poll():
        nonlocal future
        refresh()
        if not future.done():
            root.after(100,poll)
            return
        output.configure(state="normal")
        output.delete("1.0","end")
        try:
            for item in future.result():
                o=item.observation.opportunity
                output.insert("end",f"{o.title}\nValue: {o.currency} {o.amount}\nReview eligible: {item.screening.eligible_for_review}\nReasons: {item.screening.reasons}\nSynthetic data only.\n")
        except Exception as exc:
            output.insert("end",f"Screening failed: {type(exc).__name__}")
        finally:
            refresh()
            output.configure(state="disabled")
            future = None
            if not stop.is_set():
                launch.configure(state="normal")
    def halt():
        stop.set()
        launch.configure(state="disabled")
        halt_status.configure(text="HALTED — new tasks blocked")
    def resume():
        if future is None:
            stop.clear()
            launch.configure(state="normal")
            halt_status.configure(text="Offline ready")
    controls = ttk.Frame(root)
    controls.pack(pady=10)
    launch = ttk.Button(controls,text="Run offline demonstration",command=run)
    launch.pack(side="left")
    ttk.Button(controls,text="Emergency halt",command=halt).pack(side="left")
    ttk.Button(controls,text="Resume offline",command=resume).pack(side="left")
    halt_status = ttk.Label(root,text="Offline ready")
    halt_status.pack()
    root.mainloop()

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import tkinter
        result=demo()
        sys.exit(0 if len(result)==1 and result[0].screening.eligible_for_review else 1)
    main()
