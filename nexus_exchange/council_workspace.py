"""Local native Council review and historical audit, for one saved plan.

Every operation passes the trusted desktop worker gate and RuntimeGuard facade.
No automatic registration, retry, dispatch or commercial authorization.
"""
import sqlite3

from .council_audit import scope_for, validate_snapshot

CHECK_LABELS={
    "source_and_capability":"Source / declared capability",
    "financial_model":"Financial feasibility",
    "delivery_schedule":"Delivery schedule",
    "collection_timing":"Collection timing",
    "reference_coverage":"Assumption reference coverage",
}
STATE_LABELS={"LOCAL_CHECK_FITS":"Local model fits",
              "LOCAL_CHECK_FAILS":"Local check fails",
              "UNRESOLVED":"Unresolved"}
AUDIT_LABELS={"RECORDED":"Recorded historical audit",
              "LEGACY_DIGEST_ONLY":"Legacy digest only",
              "RESERVED_NO_REPORT":"Reserved; no report",
              "INTERRUPTED_NO_REPORT":"Interrupted; no report"}


class CouncilWorkspace:
    """Fixed plan; only the supplied trusted runtime facade may operate."""
    def __init__(self,plan_id,*,action,blocked_check):
        self.task_id="COUNCIL."+scope_for(plan_id)
        self.plan_id=plan_id
        if not callable(action) or not callable(blocked_check):
            raise ValueError("trusted desktop facade required")
        self._action=action
        self._blocked=blocked_check

    def _permit(self):
        if self._blocked() is not False:
            raise PermissionError("Council halted, busy or unavailable.")

    def _call(self,operation):
        self._permit()
        result=self._action(operation,self.plan_id)
        self._permit()
        if (type(result) is not dict or result.get("task_id")!=self.task_id
                or any(result.get(k) is not False for k in
                       ("external_authority","execution_eligible","commercial_facts_verified","release_eligible"))):
            raise ValueError("Council scope or authority boundary mismatch")
        return result

    def _snapshot(self,result):
        validate_snapshot(result)
        if result["plan_id"]!=self.plan_id or result["task_id"]!=self.task_id:
            raise ValueError("Council snapshot outside saved plan")
        return result

    def inspect(self):
        return self._snapshot(self._call("inspect"))

    def register(self):
        return self._call("register")

    def run_once(self):
        result=self._call("run_once")
        self._snapshot(result["snapshot"])
        if (result["ledger"]["task_id"]!=self.task_id
                or result["review"]["task_id"]!=self.task_id):
            raise ValueError("Council result outside saved plan")
        return result

    def history(self):
        result=self._call("history")
        if (result.get("historical_only") is not True or result.get("current_decision") is not False):
            raise ValueError("historical Council result required")
        for entry in result["attempts"]:
            if entry["audit"] is not None:
                self._snapshot(entry["audit"]["snapshot"])
        return result


def snapshot_text(snapshot):
    def value(raw):
        return "Unknown" if raw is None else str(raw)
    from .ranking_workspace import display_wait
    return "\n".join([
        "UNVERIFIED LOCAL REVIEW — NO COMMERCIAL AUTHORITY",
        "Saved plan: "+snapshot["plan_id"],
        "Evaluated UTC: "+snapshot["evaluated_at"],
        "Snapshot fingerprint: "+snapshot["snapshot_sha256"],
        "Declared profile: "+snapshot["context"]["profile_revision"],
        "Archived observation: "+snapshot["context"]["observation_sha256"],
        "Modeled exposure (USD): "+value(snapshot["modeled_cash_exposure"]),
        "Modeled expected net (USD): "+value(snapshot["modeled_expected_net"]),
        "Modeled collection wait: "+display_wait(snapshot["modeled_collection_wait_us"]),
        f'References noted: {snapshot["referenced"]}/{snapshot["total"]}; '
        f'unknown assumptions: {snapshot["unknown"]}; independently verified: 0',
        "Source hold: "+value(snapshot["source_hold"]),
        *[CHECK_LABELS[item["criterion"]]+": "+STATE_LABELS[item["state"]]
          for item in snapshot["criteria"]],
        "Review reasons: "+", ".join(snapshot["reasons"]),
        "Local model checks and document references do not establish commercial facts.",
    ])


def ledger_text(ledger):
    next_attempt=ledger["next_attempt"]
    return (f'{ledger["state"]} | {ledger["attempts_used"]}/3 attempts used | '
            +("No next attempt" if next_attempt is None else f"Next attempt: {next_attempt}")
            +" | Research only")


def audit_text(entry):
    audit=entry["audit"]
    lines=["HISTORICAL ONLY — No current decision or authority",
           "Attempt: "+str(entry["attempt"]),
           "Record: "+AUDIT_LABELS[entry["audit_state"]],
           "Outcome: "+str(entry["outcome"] or "Reserved"),
           "Reserved UTC: "+entry["reserved_at"],
           "Completed UTC: "+str(entry["completed_at"] or "Not completed"),
           "Report fingerprint: "+str(entry["report_sha256"] or "Unavailable"),
           "Audit fingerprint: "+str(entry["audit_sha256"] or "Unavailable")]
    if audit is not None:
        lines.extend([snapshot_text(audit["snapshot"]),"Historical criterion review:"])
        lines.extend(item["criterion"]+": "+item["reason"] for item in audit["review"]["criteria"])
        lines.append("Recorded reference IDs:")
        lines.extend(key+": "+", ".join(ids) for key,ids in audit["snapshot"]["reference_ids"].items() if ids)
    else:
        lines.append("No retained snapshot for this attempt. Nothing has been reconstructed.")
    return "\n".join(lines)


def open_council_window(parent,*,plan_id,action,blocked_check,smoke=False):
    """One saved-plan review window; history and current inspection stay separate."""
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    workspace=CouncilWorkspace(plan_id,action=action,blocked_check=blocked_check)
    window=tk.Toplevel(parent)
    window.title("Nexus Exchange | Council review and audit")
    window.geometry("1160x810")
    window.minsize(850,650)
    ttk.Label(window,text="COUNCIL — Local scenario review",font=("Segoe UI",18)).pack(pady=6)
    ttk.Label(window,text="Saved plan: "+plan_id,wraplength=1080).pack(padx=12)
    ttk.Label(window,text="Explicit reviews consume one of three attempts. No independent factual verification or external authority.",
              wraplength=1050).pack(pady=5)
    status=ttk.Label(window,text="Inspect a saved plan; register explicitly before reviewing.",wraplength=1050)
    status.pack(fill="x",padx=12,pady=3)
    controls=ttk.Frame(window)
    controls.pack(pady=5)
    tabs=ttk.Notebook(window)
    tabs.pack(fill="both",expand=True,padx=12,pady=6)
    local=ttk.Frame(tabs)
    past=ttk.Frame(tabs)
    tabs.add(local,text="Current local inspection")
    tabs.add(past,text="Historical attempt audit")
    current=ScrolledText(local,wrap="word",state="disabled")
    current.pack(fill="both",expand=True,padx=8,pady=8)
    tree=ttk.Treeview(past,columns=("attempt","outcome","audit","time"),
                      show="headings",height=4,selectmode="browse")
    for key,label,width in (("attempt","Attempt",75),("outcome","Recorded outcome",180),
        ("audit","Audit availability",240),("time","Completed UTC",285)):
        tree.heading(key,text=label)
        tree.column(key,width=width,anchor="w")
    tree.pack(fill="x",padx=8,pady=8)
    detail=ScrolledText(past,wrap="word",state="disabled")
    detail.pack(fill="both",expand=True,padx=8,pady=4)
    records={}
    timer=None
    closed=False
    has_data=False

    def write(widget,text):
        widget.configure(state="normal")
        widget.delete("1.0","end")
        widget.insert("end",text)
        widget.configure(state="disabled")

    def clear(message):
        nonlocal has_data
        has_data=False
        records.clear()
        for key in tree.get_children():
            tree.delete(key)
        write(current,"")
        write(detail,"")
        status.configure(text=message)
        attempt_button.configure(state="disabled")

    def error(exc):
        clear("Council unavailable or blocked; refresh explicitly. ("+type(exc).__name__+")")

    def update_ledger(result):
        status.configure(text=ledger_text(result))
        attempt_button.configure(state="normal" if result["next_attempt"] is not None else "disabled")

    def inspect():
        nonlocal has_data
        write(current,"")
        try:
            result=workspace.inspect()
            write(current,snapshot_text(result))
            has_data=True
            tabs.select(local)
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def register():
        nonlocal has_data
        try:
            result=workspace.register()
            has_data=True
            update_ledger(result)
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def display(_event=None):
        if blocked_check() is not False:
            clear("Council halted or busy; refresh after explicit resume.")
            return
        selected=tree.selection()
        if not selected or selected[0] not in records:
            write(detail,"")
            return
        write(detail,audit_text(records[selected[0]]))

    def show_history(result):
        nonlocal has_data
        has_data=True
        records.clear()
        for key in tree.get_children():
            tree.delete(key)
        write(detail,"")
        for row in result["attempts"]:
            key=str(row["attempt"])
            records[key]=row
            tree.insert("","end",iid=key,values=(row["attempt"],row["outcome"] or "RESERVED",
                        AUDIT_LABELS[row["audit_state"]],row["completed_at"] or ""))
        update_ledger(result)
        tabs.select(past)
        if records:
            key=list(records)[-1]
            tree.selection_set(key)
            display()

    def history():
        try:
            result=workspace.history()
            show_history(result)
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def run_once():
        nonlocal has_data
        # Clear prior current output before invoking an explicitly requested attempt.
        clear("Running one local review attempt...")
        try:
            result=workspace.run_once()
            write(current,snapshot_text(result["snapshot"])+"\nRecorded outcome: "+result["review"]["status"])
            has_data=True
            update_ledger(result["ledger"])
            tabs.select(local)
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def monitor():
        nonlocal timer
        if closed:
            return
        if blocked_check() is not False and has_data:
            clear("Council halted or busy; previous display cleared.")
        timer=window.after(250,monitor)

    def destroyed(event):
        nonlocal closed
        if event.widget is window:
            closed=True
            if timer is not None:
                try:
                    window.after_cancel(timer)
                except tk.TclError:
                    pass

    ttk.Button(controls,text="Inspect saved plan",command=inspect).pack(side="left",padx=4)
    ttk.Button(controls,text="Register review task",command=register).pack(side="left",padx=4)
    attempt_button=ttk.Button(controls,text="Run one review attempt",command=run_once,state="disabled")
    attempt_button.pack(side="left",padx=4)
    ttk.Button(controls,text="Refresh historical audit",command=history).pack(side="left",padx=4)
    tree.bind("<<TreeviewSelect>>",display)
    window.bind("<Destroy>",destroyed,add="+")
    initial=inspect()
    monitor()
    if smoke:
        if initial is None or initial["independently_verified_count"]!=0:
            raise RuntimeError("Council GUI initial inspection failed")
        state=register()
        if state is None or state["attempts_used"]!=0:
            raise RuntimeError("Council GUI explicit registration failed")
        result=run_once()
        if result is None or result["ledger"]["attempts_used"]!=1 or result["external_authority"]:
            raise RuntimeError("Council GUI explicit review failed")
        stored=history()
        window.update_idletasks()
        window.update()
        if (stored is None or len(tree.get_children())!=1
                or "HISTORICAL ONLY" not in detail.get("1.0","end")
                or result["snapshot"]["snapshot_sha256"] not in detail.get("1.0","end")):
            raise RuntimeError("Council GUI historical audit failed")
    return window
