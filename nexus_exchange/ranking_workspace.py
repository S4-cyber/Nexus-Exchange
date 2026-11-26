"""Native, offline presentation of bounded Scout ranking snapshots."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3

from .checklist_store import _context, context_for
from .owner_profile import ProfileStore, PROFILE_SOURCES, profile_revision
from .review_ranking import RankingStore
from .operator_capabilities import detail_text
from .scout_requirements_form import open_service_requirements_window
from .scenario_workspace import open_scenario_window

TIERS={
    "MODEL_FITS_UNVERIFIED":"Model fits / unverified",
    "MODEL_UNRESOLVED":"Model unresolved",
    "MODEL_DOES_NOT_FIT":"Model does not fit",
    "SOURCE_REVIEW_REQUIRED":"Source review required",
    "CONTRACTOR_INTELLIGENCE_ONLY":"Contractor intelligence only",
    "SOURCE_NOT_SELECTED":"Source not selected",
}
HOUR_US=3600*1000000


class RankingWorkspace:
    """Reload current declared profile and gate every local operation.

    A report is a timestamped snapshot, not live facts. Cross-file profile
    checks detect changes around reads, not an authenticated atomic profile.
    """
    def __init__(self,directory,*,halt_check,clock=None):
        self.directory=Path(directory)
        self.halt_check=halt_check
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _permit(self):
        if self.halt_check() is not False:
            raise PermissionError("Research halted or halt state unknown.")

    def _profile(self):
        self._permit()
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profile=profiles.load(halted=False)
        if profile is None:
            raise ValueError("Save a declared owner profile before ranking.")
        return profile

    def _confirm(self,profile):
        self._permit()
        if profile_revision(self._profile())!=profile_revision(profile):
            raise ValueError("Owner profile changed. Refresh ranking.")
        self._permit()

    def refresh(self,*,source=None,query="",limit=25,scan_limit=100,operator_focus=False):
        profile=self._profile()
        self._permit()
        with RankingStore(self.directory/"scout-leads.sqlite3") as store:
            report=store.rank_review(profile=profile,now=self.clock(),source=source,
                query=query,limit=limit,scan_limit=scan_limit,operator_focus=operator_focus,halted=False)
        self._confirm(profile)
        return report

    def review_requirements(self, context, requirements):
        """Review explicit service declarations against the current local archive."""
        self._permit()
        context = _context(context)
        profile = self._profile()
        if profile_revision(profile) != context["profile_revision"]:
            raise ValueError("Owner profile changed. Refresh ranking.")
        self._permit()
        with RankingStore(self.directory/"scout-leads.sqlite3") as store:
            result = store.review_requirements(context, requirements, profile=profile,
                now=self.clock(), halted=False)
        self._confirm(profile)
        return result

    def resolve(self,context):
        self._permit()
        context=_context(context)
        profile=self._profile()
        if profile_revision(profile)!=context["profile_revision"]:
            raise ValueError("Owner profile changed. Refresh ranking.")
        self._permit()
        with RankingStore(self.directory/"scout-leads.sqlite3") as store:
            lead=store._current(context,profile,self.clock(),False)
        self._confirm(profile)
        return lead


def display_amount(value):
    """Display exact modeled USD; never round tiny nonzero amounts to zero."""
    if value is None:
        return "Unknown"
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("finite modeled decimal required")
    text=format(value,"f")
    whole,sep,fraction=text.partition(".")
    if not sep:
        return whole+".00"
    return whole+"."+fraction.ljust(2,"0")


def display_wait(value):
    """Ceiling to elapsed hours for display, not for ranking comparisons."""
    if value is None:
        return "Unknown"
    if type(value) is not int:
        raise ValueError("modeled wait must be integer microseconds")
    if value<0:
        return "Past modeled collection"
    hours=(value+HOUR_US-1)//HOUR_US
    days,hours=divmod(hours,24)
    return f"{days}d {hours}h"


def report_summary(report):
    suffix=[]
    if report["scan_truncated"]:
        suffix.append("Scan truncated")
    if report["output_truncated"]:
        suffix.append("Display truncated")
    return (f'{report["pathway"].capitalize()} | {report["returned"]} shown / '
            f'{report["evaluated"]} evaluated / {report["matched"]} matched | '
            f'UTC {report["evaluated_at"]} | Not a global ranking'
            +(" | "+", ".join(suffix) if suffix else "")
            +f' | {report["implemented_hint_count"]} implemented title hints in scan'
            +(" | Operator focus within tier" if report["operator_focus"] else ""))


def row_values(row):
    return (row["source"],row["title"],TIERS[row["review_tier"]],
            display_amount(row["modeled_cash_exposure"]),
            display_amount(row["modeled_expected_net"]),
            display_wait(row["modeled_collection_wait_us"]))


def row_details(row,report):
    context=row["context"]
    def fit(value):
        return "Unknown" if value is None else ("Modeled fit" if value is True else "Does not fit")
    return "\n".join([
        "UNVERIFIED HISTORICAL MODEL — NO EXECUTION OR AUTHORITY",
        "Snapshot UTC: "+report["evaluated_at"],
        row["title"],"Source: "+row["source"],row["source_url"],
        "Review classification: "+TIERS[row["review_tier"]],
        "Underlying model: "+TIERS[row["model_tier"]],
        "Retrieved UTC: "+context["retrieved_at"],
        "Observation fingerprint: "+context["observation_sha256"],
        "Declared profile revision: "+context["profile_revision"],
        "Saved plan: "+(row["plan_id"] or "None / unresolved"),
        "Modeled exposure (USD): "+display_amount(row["modeled_cash_exposure"]),
        "Modeled expected net (USD): "+display_amount(row["modeled_expected_net"]),
        "Modeled wait until collection (rounded up for display): "+display_wait(row["modeled_collection_wait_us"]),
        "Declared budget: "+fit(row["modeled_budget_fit"]),
        "Modeled schedule: "+fit(row["modeled_schedule_fit"]),
        "Reasons: "+", ".join(row["reasons"]),
        "",detail_text(row["operator_capability"]),
        "Refresh before relying on this snapshot. Verify original terms and evidence independently.",
    ])


def open_ranking_window(parent,*,directory,halt_check,review_tasks=None,council_action=None,council_blocked=None,
                        operator_action=None,operator_blocked=None,csv_action=None,smoke=False):
    """Explicit-refresh Matrix; only opens local, revalidated review workspaces."""
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    workspace=RankingWorkspace(directory,halt_check=halt_check)
    from .workspace_host import open_workspace
    window, content = open_workspace(parent, "Nexus Exchange | Scout opportunity Matrix", 1160, 760, minimum=(760, 540))
    ttk.Label(content,text="SCOUT — Ranked opportunity Matrix",font=("Segoe UI",18)).pack(pady=8)
    ttk.Label(content,text="Historical snapshots and hypothetical USD assumptions only. No verified earnings, availability, or authority.",
              wraplength=1050).pack(padx=12,pady=4)
    filters=ttk.Frame(content)
    filters.pack(fill="x",padx=12,pady=6)
    source=tk.StringVar(master=window,value="All")
    query=tk.StringVar(master=window,value="")
    limit=tk.StringVar(master=window,value="25")
    operator_focus=tk.BooleanVar(master=window,value=False)
    ttk.Label(filters,text="Source").pack(side="left",padx=4)
    ttk.Combobox(filters,textvariable=source,values=("All",)+PROFILE_SOURCES,
        state="readonly",width=16).pack(side="left",padx=4)
    ttk.Label(filters,text="Search").pack(side="left",padx=4)
    ttk.Entry(filters,textvariable=query,width=32).pack(side="left",padx=4)
    ttk.Label(filters,text="Show").pack(side="left",padx=4)
    ttk.Combobox(filters,textvariable=limit,values=("25","50","100"),state="readonly",width=5).pack(side="left")
    ttk.Checkbutton(filters,text="Prioritize Operator hints",variable=operator_focus).pack(side="left",padx=5)
    status=ttk.Label(content,wraplength=1080)
    status.pack(fill="x",padx=12,pady=4)
    table=ttk.Frame(content)
    table.pack(fill="both",padx=12,pady=4)
    columns=("source","title","tier","exposure","net","wait")
    tree=ttk.Treeview(table,columns=columns,show="headings",selectmode="browse",height=11)
    for key,label,width in (("source","Source",90),("title","Historical opportunity",350),
        ("tier","Review classification",200),("exposure","Modeled cash USD",140),
        ("net","Modeled net USD",145),("wait","Modeled collection wait",165)):
        tree.heading(key,text=label)
        tree.column(key,width=width,anchor="w",stretch=False)
    yscroll=ttk.Scrollbar(table,orient="vertical",command=tree.yview)
    xscroll=ttk.Scrollbar(table,orient="horizontal",command=tree.xview)
    tree.configure(yscrollcommand=yscroll.set,xscrollcommand=xscroll.set)
    tree.grid(row=0,column=0,sticky="nsew")
    yscroll.grid(row=0,column=1,sticky="ns")
    xscroll.grid(row=1,column=0,sticky="ew")
    table.columnconfigure(0,weight=1)
    table.rowconfigure(0,weight=1)
    buttons=ttk.Frame(content)
    buttons.pack(before=table, pady=4)
    details=ScrolledText(content,height=12,wrap="word",state="disabled")
    details.pack(fill="both",expand=True,padx=12,pady=6)
    report=None
    rows={}
    timer=None
    closed=False

    def write(text):
        details.configure(state="normal")
        details.delete("1.0","end")
        details.insert("end",text)
        details.configure(state="disabled")

    def clear(text):
        nonlocal report
        report=None
        rows.clear()
        for item in tree.get_children():
            tree.delete(item)
        status.configure(text=text)
        write("")

    def refresh():
        nonlocal report
        clear("Evaluating local historical observations...")
        try:
            result=workspace.refresh(source=None if source.get()=="All" else source.get(),
                query=query.get(),limit=int(limit.get()),operator_focus=operator_focus.get())
            for index,row in enumerate(result["rows"]):
                key=str(index)
                rows[key]=row
                tree.insert("","end",iid=key,values=row_values(row))
            report=result
            status.configure(text=report_summary(result))
            if rows:
                tree.selection_set("0")
                display()
            else:
                write("No matching archived opportunities.")
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            clear("Ranking unavailable. Save a declared profile, check archive/filters and halt state. ("+type(exc).__name__+")")
            return None

    def selected():
        items=tree.selection()
        if report is None or not items or items[0] not in rows:
            raise ValueError("Refresh and select an opportunity.")
        return rows[items[0]]

    def display(_event=None):
        if halt_check() is not False:
            clear("Research halted; refresh only after explicit resume.")
            return
        try:
            row=selected()
        except ValueError:
            write("")
            return
        write(row_details(row,report))

    def navigate(kind):
        try:
            row=selected()
            current=workspace.resolve(row["context"])
            if kind=="tasks":
                return review_tasks(current,window)
            if kind=="requirements":
                return open_service_requirements_window(window,workspace,row["context"],current["title"],
                    plan_id=row["plan_id"],sample_action=csv_action,blocked_check=operator_blocked)
            return open_scenario_window(window,current,directory=directory,halt_check=halt_check,
                council_action=council_action,council_blocked=council_blocked,
                operator_action=operator_action,operator_blocked=operator_blocked,csv_action=csv_action)
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            clear("Selected context unavailable or changed; refresh ranking. ("+type(exc).__name__+")")
            return None

    def filters_changed(*_):
        clear("Filters changed; refresh to evaluate a new snapshot.")

    def guard_display():
        nonlocal timer
        if closed:
            return
        if report is not None and halt_check() is not False:
            clear("Research halted; previous snapshot cleared. Refresh after explicit resume.")
        timer=window.after(350,guard_display)

    def destroyed(event):
        nonlocal closed
        if event.widget is window:
            closed=True
            if timer is not None:
                try:
                    window.after_cancel(timer)
                except tk.TclError:
                    pass

    ttk.Button(filters,text="Refresh ranking",command=refresh).pack(side="left",padx=8)
    ttk.Button(buttons,text="Open selected lead planning",command=lambda:navigate("plan")).pack(side="left",padx=5)
    ttk.Button(buttons,text="Review service requirements",command=lambda:navigate("requirements")).pack(side="left",padx=5)
    if review_tasks is not None:
        ttk.Button(buttons,text="Review selected To Do",command=lambda:navigate("tasks")).pack(side="left",padx=5)
    tree.bind("<<TreeviewSelect>>",display)
    window.bind("<Destroy>",destroyed,add="+")
    for var in (source,query,limit,operator_focus):
        var.trace_add("write",filters_changed)
    initial=refresh()
    guard_display()
    if smoke:
        if initial is None or not initial["rows"] or len(tree.get_children())!=initial["returned"]:
            raise RuntimeError("ranking GUI did not populate")
        first=initial["rows"][0]
        if first["plan_id"] is None or first["modeled_expected_net"]!=Decimal("120"):
            raise RuntimeError("ranking GUI did not load saved financial scenario")
        if first["review_tier"]!="SOURCE_REVIEW_REQUIRED" or first["external_authority"]:
            raise RuntimeError("ranking GUI lost source hold")
        if "Operator capability:" not in details.get("1.0","end"):
            raise RuntimeError("ranking GUI missing implemented capability projection")
        if "UNVERIFIED" not in details.get("1.0","end"):
            raise RuntimeError("ranking GUI missing research boundary")
        child=navigate("plan")
        if child is None:
            raise RuntimeError("ranking GUI could not open exact lead planning")
        child.destroy()
        child=open_service_requirements_window(window,workspace,first["context"],first["title"],
            plan_id=first["plan_id"],sample_action=csv_action,blocked_check=operator_blocked,smoke=True)
        child.destroy()
        query.set("synthetic nonmatching filter")
        if tree.get_children() or report is not None:
            raise RuntimeError("ranking GUI retained old snapshot after filter change")
        filtered=refresh()
        if filtered is None or filtered["returned"]!=0:
            raise RuntimeError("ranking GUI filter failed")
        query.set("")
        if refresh() is None:
            raise RuntimeError("ranking GUI refresh failed")
        operator_focus.set(True)
        focused=refresh()
        if focused is None or focused["operator_focus"] is not True:
            raise RuntimeError("ranking GUI Operator focus failed")
    return window
