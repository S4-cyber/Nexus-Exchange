"""Native historical deliverable ledger; no customer acceptance or dispatch."""
from copy import deepcopy
import sqlite3

from .checklist_store import _hash
from .deliverable_obligations import (
    NOTE_KINDS, MAX_NOTES, _FLAGS_EXTRA, _binding, _head, _stored_stamp, _note,
)
from .lead_store import _digest, _json
from .scout import _timestamp

_RECORD_FIELDS={"obligation_id","plan_id","created_at","binding","registration_sha256",
                "head_sha256","notes","state","historical_only",*_FLAGS_EXTRA}
_NOTE_FIELDS={"obligation_id","sequence","previous_sha256","kind","reference",
              "recorded_at","event_sha256"}
_LIST_FIELDS={"plan_id","rows","truncated","historical_only",*_FLAGS_EXTRA}
_LABELS={
    "acceptance_claim_noted":"Acceptance claim — unverified",
    "revision_request_noted":"Revision request — unverified",
    "rejection_claim_noted":"Rejection claim — unverified",
}


def validate_record(raw,plan_id,expected_id=None):
    """Validate the bounded historical projection and its exact identity chain."""
    _hash(plan_id)
    if (type(raw) is not dict or set(raw)!=_RECORD_FIELDS or
            raw["plan_id"]!=plan_id or raw["historical_only"] is not True or
            any(raw[k] is not False for k in _FLAGS_EXTRA)):
        raise ValueError("invalid local obligation projection")
    key=_hash(raw["obligation_id"])
    if expected_id is not None and key!=_hash(expected_id):
        raise ValueError("obligation selection changed")
    binding=raw["binding"]
    if type(binding) is not dict:
        raise ValueError("invalid obligation binding")
    checked=_binding(binding.get("contract"),binding.get("qa_report"),binding.get("artifact_reference"))
    if (_json(binding)!=_json(checked) or checked["contract"]["plan_id"]!=plan_id
            or _head(checked)!=key):
        raise ValueError("invalid obligation identity")
    created=_stored_stamp(raw["created_at"])
    prior=_timestamp(created)
    if prior<_timestamp(checked["contract"]["context"]["retrieved_at"]):
        raise ValueError("invalid obligation registration time")
    head=_digest(_json(dict(binding=checked,created_at=created)))
    if head!=raw["registration_sha256"]:
        raise ValueError("invalid obligation registration digest")
    notes=raw["notes"]
    if type(notes) is not list or len(notes)>MAX_NOTES:
        raise ValueError("invalid historical note count")
    seen=set()
    for sequence,event in enumerate(notes,1):
        if type(event) is not dict or set(event)!=_NOTE_FIELDS:
            raise ValueError("invalid historical note")
        stamp=_timestamp(_stored_stamp(event["recorded_at"]))
        if stamp<prior:
            raise ValueError("invalid historical note order")
        payload=_json({k:v for k,v in event.items() if k!="event_sha256"})
        rebuilt=_note((sequence,payload,event["event_sha256"]),raw,head,sequence,seen,stamp)
        if _json(rebuilt)!=_json(event):
            raise ValueError("invalid historical note digest")
        head=event["event_sha256"]
        prior=stamp
        seen.add(event["reference"])
    if raw["head_sha256"]!=head or raw["state"]!=(
            "LOCAL_EVIDENCE_NOTED" if notes else "LOCAL_ARTIFACT_RECORDED"):
        raise ValueError("invalid obligation head or state")
    return deepcopy(raw)


class ObligationWorkspace:
    """Fixed saved plan, explicit list/inspection and one confirmed evidence note."""
    def __init__(self,plan_id,*,action,blocked_check):
        self.plan_id=_hash(plan_id)
        if not callable(action) or not callable(blocked_check):
            raise ValueError("trusted desktop callbacks required")
        self.action=action
        self.blocked_check=blocked_check
        self.clear()

    def clear(self):
        self._selected=None

    def _permit(self):
        if self.blocked_check() is not False:
            self.clear()
            raise PermissionError("obligation workspace halted or busy")

    @property
    def selected(self):
        return deepcopy(self._selected)

    def refresh(self,limit=100):
        self.clear()
        self._permit()
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid list limit")
        result=self.action("list",self.plan_id,limit=limit)
        self._permit()
        if (type(result) is not dict or set(result)!=_LIST_FIELDS or result["plan_id"]!=self.plan_id
                or result["historical_only"] is not True or type(result["truncated"]) is not bool
                or type(result["rows"]) is not list or len(result["rows"])>limit
                or any(result[k] is not False for k in _FLAGS_EXTRA)):
            raise ValueError("invalid obligation list")
        rows=[validate_record(row,self.plan_id) for row in result["rows"]]
        if len({row["obligation_id"] for row in rows})!=len(rows):
            raise ValueError("duplicate obligation identity")
        return dict(result,rows=rows)

    def inspect(self,key):
        self.clear()
        self._permit()
        key=_hash(key)
        result=self.action("history",self.plan_id,obligation_id=key)
        self._permit()
        self._selected=validate_record(result,self.plan_id,key)
        return self.selected

    def note(self,kind,evidence_path,*,confirmed=None):
        self._permit()
        if (confirmed is not True or self._selected is None):
            raise PermissionError("inspect exact obligation before confirmed evidence note")
        if type(kind) is not str or kind not in NOTE_KINDS:
            raise ValueError("unknown evidence note kind")
        selected=self._selected
        self.clear()
        result=self.action("note",self.plan_id,confirmed=True,
                           obligation_id=selected["obligation_id"],
                           expected_head=selected["head_sha256"],kind=kind,evidence_path=evidence_path)
        self._permit()
        current=validate_record(result,self.plan_id,selected["obligation_id"])
        if (current["registration_sha256"]!=selected["registration_sha256"]
                or len(current["notes"])!=len(selected["notes"])+1
                or current["notes"][:-1]!=selected["notes"]
                or current["notes"][-1]["kind"]!=kind):
            raise ValueError("unexpected obligation history change")
        self._selected=current
        return self.selected


def record_text(record):
    binding=record["binding"]
    qa=binding["qa_report"]
    spec=binding["contract"]["specification"]
    lines=["HISTORICAL LOCAL OBLIGATION — no verified buyer acceptance or invoice eligibility",
           "Obligation: "+record["obligation_id"],"Created UTC: "+record["created_at"],
           "Contract: "+binding["contract"]["contract_sha256"],
           "Artifact: "+binding["artifact_reference"],"QA: "+qa["report_sha256"],
           "Expected rows: "+str(spec["expected_rows"])+" | key: "+spec["key_column"],
           "Columns: "+", ".join(spec["columns"]),
           "Local checks: "+", ".join(qa["checks"]),
           "Evidence head: "+record["head_sha256"],"",
           "Evidence notes (owner declarations; file fingerprints only)"]
    if not record["notes"]:
        lines.append("No evidence notes recorded.")
    for event in record["notes"]:
        lines.extend([str(event["sequence"])+". "+_LABELS[event["kind"]]+" | "+event["recorded_at"],
                      event["reference"]])
    return "\n".join(lines)


def open_obligation_window(parent,*,plan_id,action,blocked_check,smoke=None):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    from tkinter.scrolledtext import ScrolledText

    workspace=ObligationWorkspace(plan_id,action=action,blocked_check=blocked_check)
    window=tk.Toplevel(parent)
    window.title("Nexus Exchange | Local deliverable obligations")
    window.geometry("1050x700")
    ttk.Label(window,text="OPERATOR — Historical deliverable obligations",font=("Segoe UI",18)).pack(pady=6)
    ttk.Label(window,text="Saved plan: "+plan_id,wraplength=1000).pack()
    ttk.Label(window,text="File fingerprints and declared notes only. No verified acceptance, invoicing or revenue.",wraplength=1000).pack(pady=4)
    tree=ttk.Treeview(window,columns=("id","created","state"),show="headings",height=7,selectmode="browse")
    for col,label,width in (("id","Obligation fingerprint",470),("created","Created UTC",220),("state","Local record state",250)):
        tree.heading(col,text=label)
        tree.column(col,width=width,anchor="w")
    tree.pack(fill="x",padx=12,pady=5)
    output=ScrolledText(window,state="disabled",wrap="word")
    output.pack(fill="both",expand=True,padx=12,pady=5)
    status=ttk.Label(window,text="Refresh to load local records.",wraplength=1000)
    status.pack(fill="x",padx=12,pady=4)
    bar=ttk.Frame(window); bar.pack(pady=7)
    kind=tk.StringVar(master=window,value=NOTE_KINDS[0])
    timer=None
    displayed=None

    def write(text):
        output.configure(state="normal")
        output.delete("1.0","end")
        output.insert("end",text)
        output.configure(state="disabled")

    def clear(message,*,rows=False):
        nonlocal displayed
        workspace.clear()
        displayed=None
        write("")
        note_button.configure(state="disabled")
        if rows:
            for item in tree.get_children():
                tree.delete(item)
        status.configure(text=message)

    def error(exc):
        if smoke is not None:
            raise exc
        clear("Obligation operation blocked ("+type(exc).__name__+"); refresh explicitly.",rows=True)

    def refresh():
        clear("Refreshing historical records...",rows=True)
        try:
            result=workspace.refresh()
            for row in result["rows"]:
                tree.insert("","end",iid=row["obligation_id"],values=(
                    row["obligation_id"],row["created_at"],row["state"]))
            status.configure(text=str(len(result["rows"]))+" local records"+
                (" shown; list capped." if result["truncated"] else ". Select and inspect."))
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def inspect():
        nonlocal displayed
        selected=tree.selection()
        clear("Inspect an exact selected obligation.")
        if not selected:
            return None
        try:
            record=workspace.inspect(selected[0])
            displayed=record["obligation_id"]
            write(record_text(record))
            note_button.configure(state="normal" if len(record["notes"])<MAX_NOTES else "disabled")
            status.configure(text="Historical record inspected. Any new note must be explicitly confirmed.")
            return record
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def note_to(path,confirmed):
        nonlocal displayed
        try:
            if not displayed or tree.selection()!=(displayed,):
                raise ValueError("obligation selection changed")
            current=workspace.note(kind.get(),path,confirmed=confirmed)
            write(record_text(current))
            tree.set(displayed,"state",current["state"])
            note_button.configure(state="normal" if len(current["notes"])<MAX_NOTES else "disabled")
            status.configure(text="Historical claim noted. No buyer acceptance or invoice eligibility recorded.")
            return current
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def add_note():
        if blocked_check() is not False or workspace.selected is None:
            clear("Halted, busy or no current inspected record.")
            return
        path=filedialog.askopenfilename(parent=window)
        if path and messagebox.askyesno("Record local evidence reference",
                "Record the selected file fingerprint as "+_LABELS[kind.get()]+"? This does not verify the customer or authorize invoicing.",parent=window):
            note_to(path,True)

    def selection_changed(_event):
        if displayed is not None and tree.selection()!=(displayed,):
            clear("Selection changed. Inspect the exact obligation.")

    ttk.Button(bar,text="Refresh history",command=refresh).pack(side="left",padx=4)
    ttk.Button(bar,text="Inspect selected",command=inspect).pack(side="left",padx=4)
    ttk.Combobox(bar,textvariable=kind,values=NOTE_KINDS,state="readonly",width=26).pack(side="left",padx=4)
    note_button=ttk.Button(bar,text="Record evidence note",command=add_note,state="disabled")
    note_button.pack(side="left",padx=4)
    tree.bind("<<TreeviewSelect>>",selection_changed)

    def check():
        nonlocal timer
        if blocked_check() is not False and (displayed is not None or tree.get_children()):
            clear("Halted or busy; refresh after resume.",rows=True)
        timer=window.after(100,check)

    def destroyed(event):
        if event.widget is window and timer is not None:
            window.after_cancel(timer)
            workspace.clear()

    window.bind("<Destroy>",destroyed,add="+")
    check()
    if smoke is not None:
        key,path=smoke
        result=refresh()
        if result is None or not tree.exists(key):
            raise RuntimeError("obligation native list failed")
        tree.selection_set(key)
        initial=inspect()
        if initial is None or initial["buyer_accepted"]:
            raise RuntimeError("obligation native inspect failed")
        current=note_to(str(path),True)
        if (current is None or len(current["notes"])!=len(initial["notes"])+1
                or current["buyer_accepted"] or current["invoice_eligible"]
                or "HISTORICAL LOCAL OBLIGATION" not in output.get("1.0","end")):
            raise RuntimeError("obligation native note failed")
        if inspect()!=current:
            raise RuntimeError("obligation native persistence failed")
    return window
