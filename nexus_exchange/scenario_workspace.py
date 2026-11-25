"""Native offline scenario editor controller and presentation helpers."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import re
import sqlite3

from .cash_feasibility import COSTS, _money, _bounded
from .checklist_store import _context, context_for
from .owner_profile import ProfileStore, profile_revision
from .scenario_store import ScenarioStore
from .evidence_workspace import open_evidence_window
from .council_workspace import open_council_window
from .schedule_feasibility import _optional_timestamp, _quantity

FINANCE_FIELDS=(
    ("compensation","Hypothetical compensation (USD)"),
    ("probability_delivery_bps","Delivery probability (0–10000 bp)"),
    ("probability_payment_given_delivery_bps","Payment given delivery (0–10000 bp)"),
    ("delivery_days","Delivery duration (elapsed days)"),
    ("payment_days_after_delivery","Payment delay after delivery (days)"),
    ("labor_hours","Delivery labor (hours)"),
)+tuple(("cost:"+k,k.replace("_"," ").capitalize()+" (USD)") for k in COSTS)
TIMING_FIELDS=(
    ("preparation_days","Preparation duration (elapsed days)"),
    ("preparation_hours","Preparation labor (hours)"),
    ("delivery_start","Hypothetical contract start (UTC)"),
    ("delivery_deadline","Hypothetical delivery due (UTC)"),
)
KEYS=tuple(k for k,_ in FINANCE_FIELDS+TIMING_FIELDS)


def blank_fields():
    return dict.fromkeys(KEYS,"")


def fields_for(scenario,plan):
    out=blank_fields()
    for key in KEYS:
        if key.startswith("cost:"):
            value=scenario["costs"][key[5:]]
        else:
            value=scenario[key] if key in scenario else plan[key]
        out[key]="" if value is None else str(value)
    return out


def parse_fields(fields):
    if type(fields) is not dict or set(fields)!=set(KEYS):
        raise ValueError("complete scenario form required")
    if any(type(v) is not str or len(v)>64 for v in fields.values()):
        raise ValueError("invalid bounded form field")
    values={k:v.strip() or None for k,v in fields.items()}
    def integer(key,maximum,validator):
        raw=values[key]
        if raw is None:
            return None
        if not re.fullmatch("[0-9]{1,6}",raw):
            raise ValueError("invalid integer: "+key)
        return validator(int(raw),maximum)
    def amount(key):
        value=values[key]
        _money(value)
        return value
    def stamp(key):
        value=values[key]
        _optional_timestamp(value)
        return value
    scenario=dict(currency="USD",compensation=amount("compensation"),
        probability_delivery_bps=integer("probability_delivery_bps",10000,_bounded),
        probability_payment_given_delivery_bps=integer("probability_payment_given_delivery_bps",10000,_bounded),
        delivery_days=integer("delivery_days",3650,_bounded),
        payment_days_after_delivery=integer("payment_days_after_delivery",3650,_bounded),
        labor_hours=integer("labor_hours",87600,_bounded),
        costs={k:amount("cost:"+k) for k in COSTS})
    plan=dict(preparation_days=integer("preparation_days",3650,_quantity),
              preparation_hours=integer("preparation_hours",87600,_quantity),
              delivery_start=stamp("delivery_start"),delivery_deadline=stamp("delivery_deadline"))
    return scenario,plan


class ScenarioWorkspace:
    """Trusted desktop adapter; reload declared profile before each action."""
    def __init__(self,directory,context,*,halt_check,clock=None):
        self.directory=Path(directory)
        self.context=_context(context)
        if self.context["profile_revision"] is None:
            raise ValueError("Save a declared owner profile and refresh Scout history first.")
        self.halt_check=halt_check
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _permit(self):
        if self.halt_check() is not False:
            raise PermissionError("Research halted or halt state unknown.")

    @contextmanager
    def _session(self):
        self._permit()
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profile=profiles.load(halted=False)
        if profile is None or profile_revision(profile)!=self.context["profile_revision"]:
            raise ValueError("Owner profile changed or unavailable. Refresh Scout history.")
        self._permit()
        now=self.clock()
        with ScenarioStore(self.directory/"scout-leads.sqlite3") as store:
            store._current(self.context,profile,now,False)
            self._permit()
            yield store,profile,now

    def list(self):
        with self._session() as (store,_,_now):
            return store.list(self.context,halted=False)

    def save(self,fields):
        self._permit()
        scenario,plan=parse_fields(fields)
        with self._session() as (store,profile,now):
            return store.save(self.context,scenario,plan,profile=profile,now=now,halted=False)

    def _selected(self,store,plan_id):
        saved=store.get(plan_id,halted=False)
        if saved is None or saved["context"]!=self.context:
            raise ValueError("Saved plan outside current Scout observation/profile.")
        return saved

    def load(self,plan_id):
        with self._session() as (store,_,_now):
            saved=self._selected(store,plan_id)
            return fields_for(saved["scenario"],saved["plan"])

    def evaluate(self,plan_id):
        with self._session() as (store,profile,now):
            self._selected(store,plan_id)
            return store.evaluate(plan_id,profile=profile,now=now,halted=False)


def summary_text(result):
    cash=result["cash"]
    timing=result["schedule"]
    def value(raw):
        return "Unknown" if raw is None else str(raw)
    def fit(raw):
        return "Unknown" if raw is None else "Modeled fit" if raw is True else "Does not fit"
    return "\n".join([
        "UNVERIFIED HYPOTHETICAL MODEL — NO EXECUTION OR AUTHORITY",
        "Plan: "+result["plan_id"],"Evaluated UTC: "+result["evaluated_at"],
        "Modeled pre-payment exposure (USD): "+value(cash["modeled_cash_exposure"]),
        "Modeled expected net (USD): "+value(cash["modeled_expected_net"]),
        "Declared budget: "+fit(cash["modeled_budget_fit"]),
        "Submission timing: "+fit(timing["modeled_submission_fit"]),
        "Delivery timing: "+fit(timing["modeled_delivery_deadline_fit"]),
        "Overall schedule: "+fit(timing["modeled_schedule_fit"]),
        "Modeled delivery finish UTC: "+value(timing["modeled_delivery_finish"]),
        "Preparation labor: "+fit(timing["modeled_preparation_hours_fit"]),
        "Delivery labor: "+fit(timing["modeled_delivery_hours_fit"]),
        "Review reasons: "+", ".join(dict.fromkeys(cash["reasons"]+timing["reasons"])),
    ])


def open_scenario_window(parent,row,*,directory,halt_check,council_action=None,council_blocked=None,smoke=False):
    """Local Tk window. No implicit save, evaluation, external action or network."""
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    workspace=ScenarioWorkspace(directory,context_for(row),halt_check=halt_check)
    records=workspace.list()
    window=tk.Toplevel(parent)
    window.title("Nexus Exchange | Scout scenario planning")
    window.geometry("1100x850")
    window.minsize(850,650)
    ttk.Label(window,text="SCOUT — Hypothetical financial and delivery plan",
              font=("Segoe UI",18)).pack(pady=6)
    ttk.Label(window,text=row["title"],wraplength=1020).pack(padx=12)
    ttk.Label(window,text="Blank = unknown, not zero. All values are owner assumptions; no income, budget or authorization is verified.",
              wraplength=1020).pack(pady=4)
    values={key:tk.StringVar(master=window,value="") for key in KEYS}
    body=ttk.Frame(window)
    body.pack(fill="x",padx=10,pady=4)
    for col,(title,fields) in enumerate((("Financial assumptions",FINANCE_FIELDS),("Preparation and delivery",TIMING_FIELDS))):
        panel=ttk.LabelFrame(body,text=title)
        panel.grid(row=0,column=col,sticky="nsew",padx=5)
        body.columnconfigure(col,weight=1)
        panel.columnconfigure(1,weight=1)
        for i,(key,label) in enumerate(fields):
            ttk.Label(panel,text=label).grid(row=i,column=0,sticky="w",padx=4,pady=2)
            ttk.Entry(panel,textvariable=values[key],width=26).grid(row=i,column=1,sticky="ew",padx=4,pady=2)
        if col==1:
            ttk.Label(panel,text="Timestamp format: YYYY-MM-DDTHH:MM:SSZ (or explicit offset).\nThe notice cutoff is for submission, not a delivery due date.",
                      wraplength=400,justify="left").grid(row=len(fields),column=0,columnspan=2,sticky="w",padx=5,pady=8)
    tree=ttk.Treeview(window,columns=("created","id","compensation"),show="headings",height=4,selectmode="browse")
    for key,label,width in (("created","Created UTC",250),("id","Saved plan fingerprint",430),("compensation","Hypothetical USD",160)):
        tree.heading(key,text=label)
        tree.column(key,width=width,anchor="w")
    tree.pack(fill="x",padx=12,pady=4)
    status=ttk.Label(window,wraplength=1020)
    status.pack(fill="x",padx=12)
    buttons=ttk.Frame(window)
    buttons.pack(pady=5)
    output=ScrolledText(window,height=9,wrap="word",state="disabled")
    output.pack(fill="both",expand=True,padx=12,pady=6)

    displayed_plan=None
    def write(text):
        nonlocal displayed_plan
        if not text:
            displayed_plan=None
        output.configure(state="normal")
        output.delete("1.0","end")
        output.insert("end",text)
        output.configure(state="disabled")
    def invalidate(*_):
        write("")
        status.configure(text="Model output cleared. Save or select a saved plan for reassessment.")
    for var in values.values():
        var.trace_add("write",invalidate)
    def populate(fields):
        for key in KEYS:
            values[key].set(fields[key])
    def show_records(rows,selected=None):
        for item in tree.get_children():
            tree.delete(item)
        for item in rows:
            key=item["plan_id"]
            fee=item["scenario"]["compensation"]
            tree.insert("","end",iid=key,values=(item["created_at"],key,"Unknown" if fee is None else fee))
        if selected is not None and tree.exists(selected):
            tree.selection_set(selected)
        status.configure(text=f"{len(rows)} saved plans shown (maximum 100); explicit reassessment required.")
    def selection():
        items=tree.selection()
        if not items:
            raise ValueError("Select a saved plan first.")
        return items[0]
    def error(exc):
        write("")
        status.configure(text="Scenario operation blocked or unavailable. Check fields, refresh history/profile and ensure research is not halted. ("+type(exc).__name__+")")
    def refresh():
        write("")
        try:
            show_records(workspace.list())
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            show_records([])
            error(exc)
    def save():
        write("")
        try:
            key=workspace.save({k:v.get() for k,v in values.items()})
            show_records(workspace.list(),key)
            status.configure(text="Immutable hypothetical plan saved. No authority; reassess explicitly.")
            return key
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            error(exc)
            return None
    def load():
        write("")
        try:
            key=selection()
            populate(workspace.load(key))
            status.configure(text="Saved plan loaded. Edits create a new immutable scenario.")
            return True
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            error(exc)
            return False
    def evaluate():
        nonlocal displayed_plan
        write("")
        try:
            key=selection()
            # Evaluate the saved record, not unsaved form changes.
            populate(workspace.load(key))
            result=workspace.evaluate(key)
            write(summary_text(result))
            displayed_plan=key
            status.configure(text="Saved plan reassessed at the displayed UTC time. Research only.")
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            error(exc)
            return None
    def evidence(smoke_test=False):
        try:
            key=selection()
            # Resolve saved context; unsaved form edits are never evidence inputs.
            workspace.load(key)
            return open_evidence_window(window,directory=directory,context=workspace.context,
                plan_id=key,halt_check=halt_check,smoke=smoke_test)
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            error(exc)
            return None
    def council(smoke_test=False):
        try:
            key=selection()
            workspace.load(key)
            return open_council_window(window,plan_id=key,action=council_action,
                blocked_check=council_blocked,smoke=smoke_test)
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None
    def new():
        tree.selection_remove(*tree.selection())
        populate(blank_fields())
    for label,callback in (("New / clear form",new),("Save immutable plan",save),
                           ("Load selected",load),("Reassess selected saved plan",evaluate),
                           ("Assumption evidence",evidence),("Refresh list",refresh)):
        ttk.Button(buttons,text=label,command=callback).pack(side="left",padx=4)
    if council_action is not None:
        ttk.Button(buttons,text="Council review",command=council).pack(side="left",padx=4)
    def selection_changed(_event):
        # Delayed Tk selection events must not erase the just-evaluated plan.
        items=tree.selection()
        if displayed_plan is not None and (not items or items[0]!=displayed_plan):
            invalidate()
    tree.bind("<<TreeviewSelect>>",selection_changed)
    show_records(records)
    if smoke:
        fields=blank_fields()
        stamp=datetime.now(timezone.utc)
        fields.update(compensation="200",probability_delivery_bps="8000",
            probability_payment_given_delivery_bps="7500",delivery_days="7",
            payment_days_after_delivery="30",labor_hours="10",preparation_days="2",
            preparation_hours="4",delivery_start=(stamp+timedelta(days=8)).isoformat(),
            delivery_deadline=(stamp+timedelta(days=16)).isoformat())
        fields.update({"cost:"+k:"0" for k in COSTS})
        populate(fields)
        key=save()
        if key is None or not tree.exists(key):
            raise RuntimeError("scenario GUI failed to save")
        new()
        refresh()
        tree.selection_set(key)
        if not load() or values["compensation"].get()!="200.00":
            raise RuntimeError("scenario GUI failed to reload")
        result=evaluate()
        if result is None or result["external_authority"] or result["cash"]["modeled_expected_net"]!=120:
            raise RuntimeError("scenario GUI failed to reassess")
        window.update_idletasks()
        window.update()
        if "UNVERIFIED" not in output.get("1.0","end"):
            raise RuntimeError("scenario GUI result missing research boundary")
        evidence_window=evidence(smoke_test=True)
        if evidence_window is None:
            raise RuntimeError("scenario GUI could not open saved-plan evidence")
        evidence_window.destroy()
        if council_action is not None:
            council_window=council(smoke_test=True)
            if council_window is None:
                raise RuntimeError("scenario GUI could not open saved-plan Council")
            council_window.destroy()
    return window
