"""Local native Council review and historical audit, for one saved plan.

Every operation passes the trusted desktop worker gate and RuntimeGuard facade.
No automatic registration, retry, dispatch or commercial authorization.
"""
import sqlite3

from .council_audit import scope_for, validate_snapshot
from .context_packet import build_packet, packet_text, LEVELS

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

    def context(self,level):
        """Fresh, bounded local context; does not register or consume an attempt."""
        self._permit()
        snapshot=self.inspect()
        result=build_packet(snapshot,level,halted=False)
        self._permit()
        return result, snapshot

    def advisory_status(self):
        """Historical attempt budget only; cannot launch or reserve a worker."""
        result=self._call("advisory_status")
        state=result.get("state")
        used=result.get("attempts_used")
        next_attempt=result.get("next_attempt")
        if (result.get("plan_id")!=self.plan_id
                or result.get("historical_only") is not True
                or any(result.get(key) is not False for key in
                       ("current_decision","independently_verified","dispatch_enabled"))
                or type(state) is not str or type(used) is not int or not 0<=used<=3):
            raise ValueError("invalid advisory budget")
        valid=((state=="NOT_STARTED" and used==0 and type(next_attempt) is int and next_attempt==1)
               or (state in ("INTERRUPTED","FAILED") and 1<=used<3
                   and type(next_attempt) is int and next_attempt==used+1)
               or (state in ("REVIEWED","RESERVED") and 1<=used<=3 and next_attempt is None)
               or (state=="ESCALATED" and used==3 and next_attempt is None))
        if not valid:
            raise ValueError("invalid advisory budget transition")
        return result

    def launch_advisory(self, confirm):
        """Explicit consent; desktop owns asynchronous collection."""
        self._permit()
        if not callable(confirm):
            raise ValueError("explicit confirmation callback required")
        preview=self._action("advisory_prepare",self.plan_id)
        self._permit()
        def hex_id(value,length):
            return (type(value) is str and len(value)==length
                    and all(ch in "0123456789abcdef" for ch in value))
        if (type(preview) is not dict or set(preview)!={
                "preview_id","plan_id","next_attempt","snapshot_sha256",
                "synthetic_only","external_authority","dispatch_enabled"}
                or preview["plan_id"]!=self.plan_id
                or not hex_id(preview["preview_id"],32)
                or not hex_id(preview["snapshot_sha256"],64)
                or type(preview["next_attempt"]) is not int
                or not 1<=preview["next_attempt"]<=3
                or preview["synthetic_only"] is not True
                or preview["external_authority"] is not False
                or preview["dispatch_enabled"] is not False):
            raise ValueError("invalid synthetic advisory preview")
        if confirm(dict(preview)) is not True:
            return None
        self._permit()
        return self._action("advisory_start",self.plan_id,
                            preview_id=preview["preview_id"],confirmed=True)

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
    from tkinter import ttk, messagebox
    from tkinter.scrolledtext import ScrolledText

    workspace=CouncilWorkspace(plan_id,action=action,blocked_check=blocked_check)
    from .cockpit import install_cockpit, fit_geometry
    window=tk.Toplevel(parent)
    content=install_cockpit(window).content
    window.title("Nexus Exchange | Council review and audit")
    window.geometry(fit_geometry(window,1160,810))
    window.minsize(850,650)
    ttk.Label(content,text="COUNCIL — Local scenario review",font=("Segoe UI",18)).pack(pady=6)
    ttk.Label(content,text="Saved plan: "+plan_id,wraplength=1080).pack(padx=12)
    ttk.Label(content,text="Explicit reviews consume one of three attempts. No independent factual verification or external authority.",
              wraplength=1050).pack(pady=5)
    status=ttk.Label(content,text="Inspect a saved plan; register explicitly before reviewing.",wraplength=1050)
    status.pack(fill="x",padx=12,pady=3)
    controls=ttk.Frame(content)
    controls.pack(pady=5)
    tabs=ttk.Notebook(content)
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

    def show_context(level):
        nonlocal has_data
        write(current,"")
        try:
            packet,snapshot=workspace.context(level)
            write(current,packet_text(packet,snapshot,halted=False))
            has_data=True
            tabs.select(local)
            return packet
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def show_advisory_status():
        nonlocal has_data
        clear("Inspecting local advisory budget...")
        try:
            result=workspace.advisory_status()
            next_attempt=result["next_attempt"]
            write(current,"SYNTHETIC ADVISORY — HISTORICAL BUDGET ONLY\n"
                  +f'Saved plan: {plan_id}\nState: {result["state"]}\n'
                  +f'Attempts used: {result["attempts_used"]}/3\n'
                  +("No remaining attempt" if next_attempt is None else f"Next possible attempt: {next_attempt}")
                  +"\nNo model, worker launch, reservation, factual verification or commercial authority. "
                   "This inspection is not consent to execute.")
            status.configure(text="Advisory budget inspected; no attempt consumed.")
            has_data=True
            tabs.select(local)
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def launch_advisory():
        clear("Preparing one synthetic advisory attempt...")
        def confirm(preview):
            return messagebox.askyesno("Run fixed offline fixture?",
                f'Saved plan: {plan_id}\nAttempt {preview["next_attempt"]} of 3\n'
                f'Snapshot: {preview["snapshot_sha256"]}\n\n'
                "This consumes one saved-plan advisory attempt. A fixed synthetic child "
                "will run, not an AI model. No network, outreach or commercial authority. "
                "Use Emergency halt on the main window to stop it. Continue?",
                parent=window,default="no")
        try:
            ticket=workspace.launch_advisory(confirm)
            status.configure(text=("Cancelled — no attempt started." if ticket is None else
                "Synthetic fixture started. See main window status and use Emergency halt if needed."))
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)

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
    context_controls=ttk.Frame(local)
    context_controls.pack(before=current, pady=4)
    ttk.Label(context_controls,text="Fresh local context:").pack(side="left",padx=4)
    ttk.Button(context_controls,text="Advisory attempt status",command=show_advisory_status).pack(side="right",padx=3)
    ttk.Button(controls,text="Run synthetic advisory",command=launch_advisory).pack(side="right",padx=4)
    for level in LEVELS:
        ttk.Button(context_controls,text=level.title(),command=lambda chosen=level:show_context(chosen)).pack(side="left",padx=3)
    tree.bind("<<TreeviewSelect>>",display)
    window.bind("<Destroy>",destroyed,add="+")
    initial=inspect()
    monitor()
    if smoke:
        if initial is None or initial["independently_verified_count"]!=0:
            raise RuntimeError("Council GUI initial inspection failed")
        budget=show_advisory_status()
        if (budget is None or budget["state"]!="NOT_STARTED" or budget["attempts_used"]!=0
                or "HISTORICAL BUDGET ONLY" not in current.get("1.0","end")):
            raise RuntimeError("Council GUI advisory budget inspection failed")
        if workspace.launch_advisory(lambda preview: False) is not None:
            raise RuntimeError("Declined synthetic advisory consent dispatched")
        if workspace.advisory_status()["attempts_used"]!=0:
            raise RuntimeError("Declined synthetic advisory consent consumed an attempt")
        for level in LEVELS:
            packet=show_context(level)
            if (packet is None or packet["level"]!=level or packet["external_authority"]
                    or "NOT INSTRUCTIONS" not in current.get("1.0","end")):
                raise RuntimeError("Council GUI context projection failed")
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
