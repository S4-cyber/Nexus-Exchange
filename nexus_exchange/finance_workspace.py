"""Native per-plan simulated receivables view; never a real financial dashboard."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import sqlite3

from .checklist_store import _hash
from .deliverable_obligations import _stored_stamp
from .lead_store import _digest, _json
from .obligation_workspace import validate_record as validate_obligation
from .scout import _timestamp
from .simulated_receivables import (
    MAX_RECEIPTS, _FLAGS, _EVENT_FIELDS, _validate_invoice, _date,
    _positive_cents, _cents, _reference,
)

_RECORD={"invoice","created_at","registration_sha256","head_sha256","receipts",
         "simulated_received_cents","simulated_outstanding_cents","state",
         "historical_only",*_FLAGS}


def validate_record(raw,plan_id,obligation):
    """Reconstruct balances and hash chain; do not trust a rendered total."""
    obligation=validate_obligation(obligation,plan_id)
    if (type(raw) is not dict or set(raw)!=_RECORD or raw["historical_only"] is not True
            or any(raw[k] is not False for k in _FLAGS)):
        raise ValueError("invalid simulated record projection")
    invoice=_validate_invoice(raw["invoice"])
    binding=obligation["binding"]
    expected=dict(plan_id=plan_id,obligation_id=obligation["obligation_id"],
        contract_sha256=binding["contract"]["contract_sha256"],
        qa_report_sha256=binding["qa_report"]["report_sha256"],
        artifact_sha256=binding["qa_report"]["artifact_sha256"],
        scenario_sha256=binding["contract"]["scenario_sha256"])
    if any(invoice[k]!=v for k,v in expected.items()):
        raise ValueError("invoice belongs to a different obligation or plan")
    created=_stored_stamp(raw["created_at"])
    prior_time=_timestamp(created)
    if prior_time<_timestamp(obligation["created_at"]):
        raise ValueError("invoice registration predates obligation")
    head=_digest(_json(dict(invoice=invoice,created_at=created)))
    if head!=raw["registration_sha256"]:
        raise ValueError("invalid invoice registration digest")
    notes=obligation["notes"]
    # An old invoice is readable after evidence changes, but the pinned head
    # must still identify an actual acceptance-claim event in this chain.
    pinned=[n for n in notes if n["event_sha256"]==invoice["obligation_head_sha256"]]
    if (len(pinned)!=1 or pinned[0]["kind"]!="acceptance_claim_noted"
            or _timestamp(pinned[0]["recorded_at"])>prior_time
            or _date(invoice["issue_date"])<_timestamp(pinned[0]["recorded_at"]).date()):
        raise ValueError("invoice evidence scope mismatch")
    receipts=raw["receipts"]
    if type(receipts) is not list or len(receipts)>MAX_RECEIPTS:
        raise ValueError("invalid simulated receipt count")
    prior_date=_date(invoice["issue_date"])
    refs=set()
    paid=0
    for seq,event in enumerate(receipts,1):
        if type(event) is not dict or set(event)!=_EVENT_FIELDS|{"event_sha256"}:
            raise ValueError("invalid simulated receipt projection")
        stamp=_timestamp(_stored_stamp(event["recorded_at"]))
        day=_date(event["paid_on"])
        ref=_reference(event["sim_reference"])
        amount=_positive_cents(event["amount_cents"])
        digest=_digest(_json({k:v for k,v in event.items() if k!="event_sha256"}))
        if (event["invoice_id"]!=invoice["invoice_id"] or type(event["sequence"]) is not int
                or event["sequence"]!=seq or event["previous_sha256"]!=head
                or event["event_sha256"]!=digest or day<prior_date or stamp<prior_time
                or ref in refs):
            raise ValueError("simulated receipt chain mismatch")
        paid+=amount
        if paid>invoice["gross_cents"]:
            raise ValueError("simulated overpayment")
        refs.add(ref)
        head=digest
        prior_date,prior_time=day,stamp
    remaining=invoice["gross_cents"]-paid
    state="SIMULATED_SETTLED" if not remaining else "SIMULATED_PARTIAL" if paid else "SIMULATED_UNPAID"
    if (raw["head_sha256"]!=head or raw["state"]!=state
            or type(raw["simulated_received_cents"]) is not int
            or type(raw["simulated_outstanding_cents"]) is not int
            or raw["simulated_received_cents"]!=paid or raw["simulated_outstanding_cents"]!=remaining):
        raise ValueError("simulated balance projection mismatch")
    return deepcopy(raw)


def aging(record,obligation,as_of):
    """As-of model calendar, not real accounting or an actual overdue notice."""
    checked=validate_record(record,obligation["plan_id"],obligation)
    invoice=checked["invoice"]
    day=_date(as_of)
    issued,due=_date(invoice["issue_date"]),_date(invoice["due_date"])
    included=sum(e["amount_cents"] for e in checked["receipts"] if _date(e["paid_on"])<=day)
    face=invoice["gross_cents"] if day>=issued else 0
    remaining=face-included
    days=max(0,(day-due).days) if remaining else 0
    if day<issued:
        status="SIM_NOT_YET_ISSUED"
    elif remaining==0:
        status="SIM_SETTLED_AS_OF"
    elif days:
        status="SIM_OVERDUE"
    else:
        status="SIM_DUE_TODAY" if day==due else "SIM_NOT_DUE"
    payload=dict(format="nexus-simulated-aging-v1",as_of=as_of,invoice_id=invoice["invoice_id"],
        receipt_head_sha256=checked["head_sha256"],obligation_head_sha256=obligation["head_sha256"],
        simulated_face_as_of_cents=face,simulated_received_as_of_cents=included,
        simulated_outstanding_as_of_cents=remaining,
        future_dated_receipts_cents=checked["simulated_received_cents"]-included,
        simulated_overdue_cents=remaining if days else 0,days_overdue=days,status=status,
        evidence_changed=invoice["obligation_head_sha256"]!=obligation["head_sha256"],
        **dict.fromkeys(_FLAGS,False))
    return dict(payload,projection_sha256=_digest(_json(payload)))


def usd(cents):
    if type(cents) is not int or cents<0:
        raise ValueError("nonnegative exact cents required")
    return f"USD {cents//100:,}.{cents%100:02d}"


class FinanceWorkspace:
    """Exact selected obligation, explicit preview/create/refresh/synthetic receipt."""
    def __init__(self,obligation,*,action,blocked_check):
        self.obligation=validate_obligation(obligation,_hash(obligation["plan_id"]))
        self.plan_id=self.obligation["plan_id"]
        if not callable(action) or not callable(blocked_check):
            raise ValueError("trusted desktop callbacks required")
        self.action=action
        self.blocked_check=blocked_check
        self.clear()

    def clear(self):
        self._preview=None
        self._record=None

    def _permit(self):
        if self.blocked_check() is not False:
            self.clear()
            raise PermissionError("simulated finance halted or busy")

    @property
    def record(self):
        return deepcopy(self._record)

    @property
    def previewed(self):
        return deepcopy(self._preview)

    @property
    def can_pay(self):
        return (self._record is not None and self._record["simulated_outstanding_cents"]>0
                and len(self._record["receipts"])<MAX_RECEIPTS
                and self._record["invoice"]["obligation_head_sha256"]==self.obligation["head_sha256"])

    def refresh(self):
        self.clear()
        self._permit()
        result=self.action("find",self.plan_id)
        self._permit()
        if result is not None:
            self._record=validate_record(result,self.plan_id,self.obligation)
        return self.record

    def preview(self,issue_date):
        self.clear()
        self._permit()
        _date(issue_date)
        if not self.obligation["notes"] or self.obligation["notes"][-1]["kind"]!="acceptance_claim_noted":
            raise ValueError("inspect latest acceptance claim before simulation")
        result=self.action("preview",self.plan_id,obligation_id=self.obligation["obligation_id"],
            expected_obligation_head=self.obligation["head_sha256"],issue_date=issue_date)
        self._permit()
        invoice=_validate_invoice(result)
        b=self.obligation["binding"]
        expected=dict(plan_id=self.plan_id,obligation_id=self.obligation["obligation_id"],
            obligation_head_sha256=self.obligation["head_sha256"],issue_date=issue_date,
            contract_sha256=b["contract"]["contract_sha256"],qa_report_sha256=b["qa_report"]["report_sha256"],
            artifact_sha256=b["qa_report"]["artifact_sha256"],scenario_sha256=b["contract"]["scenario_sha256"])
        if any(invoice[k]!=v for k,v in expected.items()):
            raise ValueError("simulation preview scope mismatch")
        self._preview=deepcopy(invoice)
        return self.previewed

    def create(self,*,confirmed=None):
        self._permit()
        if confirmed is not True or self._preview is None:
            raise PermissionError("explicit current simulation preview confirmation required")
        preview=self._preview
        self.clear()
        result=self.action("create",self.plan_id,obligation_id=preview["obligation_id"],
            expected_obligation_head=preview["obligation_head_sha256"],issue_date=preview["issue_date"],
            expected_invoice_id=preview["invoice_id"],confirmed=True)
        self._permit()
        record=validate_record(result,self.plan_id,self.obligation)
        if record["invoice"]!=preview:
            raise ValueError("created simulation differs from preview")
        self._record=record
        return self.record

    def payment(self,reference,amount,paid_on,*,confirmed=None):
        self._permit()
        if confirmed is not True or not self.can_pay:
            raise PermissionError("refresh an eligible local simulation before confirmed synthetic receipt")
        cents=_cents(amount)
        _reference(reference)
        _date(paid_on)
        old=self._record
        self.clear()
        result=self.action("payment",self.plan_id,invoice_id=old["invoice"]["invoice_id"],
            expected_head=old["head_sha256"],sim_reference=reference,amount=amount,
            paid_on=paid_on,confirmed=True)
        self._permit()
        current=validate_record(result,self.plan_id,self.obligation)
        if (current["invoice"]!=old["invoice"] or current["registration_sha256"]!=old["registration_sha256"]
                or len(current["receipts"])!=len(old["receipts"])+1
                or current["receipts"][:-1]!=old["receipts"]):
            raise ValueError("unexpected simulated receipt history change")
        event=current["receipts"][-1]
        if (event["sim_reference"],event["amount_cents"],event["paid_on"])!=(reference,cents,paid_on):
            raise ValueError("synthetic receipt differs from confirmed values")
        self._record=current
        return self.record

    def projection(self,as_of):
        self._permit()
        if self._record is None:
            raise ValueError("refresh a saved simulated invoice")
        return aging(self._record,self.obligation,as_of)

    def cashflow(self,as_of,reserve_bps):
        from .cashflow_projection import parse_reserve, validate_projection
        self._permit()
        if self._record is None:
            raise ValueError("refresh saved simulation before cash-flow modeling")
        _date(as_of)
        bps=parse_reserve(reserve_bps)
        record=self._record
        try:
            result=self.action("cashflow",self.plan_id,invoice_id=record["invoice"]["invoice_id"],
                expected_head=record["head_sha256"],expected_obligation_head=self.obligation["head_sha256"],
                as_of=as_of,reserve_bps=bps)
            self._permit()
            return validate_projection(result,record,self.obligation,as_of=as_of,reserve_bps=bps)
        except Exception:
            self.clear()
            raise


def invoice_text(invoice):
    return "\n".join(["SIMULATION ONLY — not an invoice, receivable or available funds",
        "Invoice fingerprint: "+invoice["invoice_id"],"Obligation: "+invoice["obligation_id"],
        "Modeled gross: "+usd(invoice["gross_cents"]),
        "Assumed issue date: "+invoice["issue_date"],"Modeled due date: "+invoice["due_date"],
        "No actual buyer acceptance, payment, revenue or spending authority."])


def record_text(record,projection):
    lines=[invoice_text(record["invoice"]),"",
        "Recorded synthetic receipts (all model dates): "+usd(record["simulated_received_cents"]),
        "Unallocated modeled balance (all dates): "+usd(record["simulated_outstanding_cents"]),
        "As-of model date: "+projection["as_of"]+" | "+projection["status"],
        "Simulated amount received as of date: "+usd(projection["simulated_received_as_of_cents"]),
        "Simulated outstanding as of date: "+usd(projection["simulated_outstanding_as_of_cents"]),
        "Future-dated receipts excluded: "+usd(projection["future_dated_receipts_cents"]),
        "Simulated overdue: "+usd(projection["simulated_overdue_cents"])+" | days: "+str(projection["days_overdue"]),
        "Evidence scope: "+("CHANGED — historical read only" if projection["evidence_changed"] else "Pinned local note; still unverified"),
        "","Synthetic receipt history"]
    for row in record["receipts"]:
        lines.append(row["sim_reference"]+" | "+row["paid_on"]+" | "+usd(row["amount_cents"]))
    return "\n".join(lines)


def open_finance_window(parent,*,obligation,action,blocked_check,smoke=False):
    import tkinter as tk
    from tkinter import ttk,messagebox
    from tkinter.scrolledtext import ScrolledText

    workspace=FinanceWorkspace(obligation,action=action,blocked_check=blocked_check)
    from .cockpit import install_cockpit, fit_geometry
    window=tk.Toplevel(parent)
    install_cockpit(window)
    window.title("Nexus Exchange | Simulated receivables")
    window.geometry(fit_geometry(window,1040,760))
    ttk.Label(window,text="OPERATOR — Simulated receivables",font=("Segoe UI",18)).pack(pady=6)
    ttk.Label(window,text="One saved plan; hypothetical USD only. Never a real invoice, bank balance, or received revenue.",wraplength=980).pack(pady=4)
    ttk.Label(window,text="Obligation: "+obligation["obligation_id"],wraplength=980).pack()
    today=datetime.now(timezone.utc).date().isoformat()
    issue=tk.StringVar(master=window,value=today)
    asof=tk.StringVar(master=window,value=today)
    reference=tk.StringVar(master=window,value="")
    amount=tk.StringVar(master=window,value="")
    paid=tk.StringVar(master=window,value=today)
    reserve=tk.StringVar(master=window,value="")
    form=ttk.Frame(window); form.pack(fill="x",padx=12,pady=5)
    for i,(label,var) in enumerate((("Assumed issue date (YYYY-MM-DD)",issue),
        ("As-of model date",asof),("Synthetic reference (SIM-... uppercase)",reference),
        ("Synthetic receipt USD",amount),("Synthetic receipt date",paid),
        ("Hypothetical reserve share (0–10000 bp)",reserve))):
        ttk.Label(form,text=label).grid(row=i,column=0,sticky="w",pady=3)
        ttk.Entry(form,textvariable=var,width=34).grid(row=i,column=1,sticky="w",padx=8)
    output=ScrolledText(window,state="disabled",wrap="word")
    output.pack(fill="both",expand=True,padx=12,pady=6)
    status=ttk.Label(window,text="Refresh history or explicitly preview a simulation.",wraplength=980)
    status.pack(fill="x",padx=12)
    bar=ttk.Frame(window); bar.pack(pady=7)
    timer=None

    def write(text):
        output.configure(state="normal")
        output.delete("1.0","end")
        output.insert("end",text)
        output.configure(state="disabled")

    def buttons():
        create_button.configure(state="normal" if workspace.previewed is not None else "disabled")
        receipt_button.configure(state="normal" if workspace.can_pay else "disabled")
        asof_button.configure(state="normal" if workspace.record is not None else "disabled")
        cashflow_button.configure(state="normal" if workspace.record is not None else "disabled")

    def clear(message):
        workspace.clear()
        write("")
        buttons()
        status.configure(text=message)

    def error(exc):
        if smoke:
            raise exc
        clear("Simulation blocked ("+type(exc).__name__+"); refresh obligation and ledger. No actual financial action.")

    def show(record):
        if record is None:
            write("No saved simulation for this plan.")
        else:
            write(record_text(record,workspace.projection(asof.get())))
        buttons()

    def refresh():
        clear("Refreshing local simulation...")
        try:
            record=workspace.refresh()
            show(record)
            status.configure(text="Historical simulation only; refresh obligation separately if evidence changes.")
            return record
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def preview():
        clear("Building hypothetical invoice...")
        try:
            result=workspace.preview(issue.get())
            write(invoice_text(result))
            buttons()
            status.configure(text="Review exact modeled terms before saving a local simulation.")
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def create(confirmed):
        try:
            result=workspace.create(confirmed=confirmed)
            show(result)
            status.configure(text="Local simulation saved; no real invoice issued.")
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def receive(confirmed):
        try:
            # Validate view date before mutation so display errors cannot be
            # mistaken for a rejected, but already committed, receipt.
            _date(asof.get())
            result=workspace.payment(reference.get(),amount.get(),paid.get(),confirmed=confirmed)
            show(result)
            status.configure(text="Synthetic receipt saved; no funds received.")
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def project():
        try:
            show(workspace.record)
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)

    def cashflow():
        from .cashflow_projection import projection_text
        try:
            report=workspace.cashflow(asof.get(),reserve.get())
            write(record_text(workspace.record,workspace.projection(asof.get()))+"\n\n"+projection_text(report))
            status.configure(text="Hypothetical allocation only; no balance or transfer authorization.")
            buttons()
            return report
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            error(exc)
            return None

    def confirm_create():
        if workspace.previewed is not None and messagebox.askyesno("Save simulated invoice",
                "Save these hypothetical terms only? No actual invoice or claim for payment.",parent=window):
            # Validate display date before save.
            try:
                _date(asof.get())
            except ValueError as exc:
                error(exc)
                return
            create(True)

    def confirm_receipt():
        if workspace.can_pay and messagebox.askyesno("Record synthetic receipt",
                "Record only a simulated payment event? Do not enter a real payment reference.",parent=window):
            receive(True)

    ttk.Button(bar,text="Refresh ledger",command=refresh).pack(side="left",padx=4)
    ttk.Button(bar,text="Preview simulation",command=preview).pack(side="left",padx=4)
    create_button=ttk.Button(bar,text="Save simulation",command=confirm_create,state="disabled")
    create_button.pack(side="left",padx=4)
    receipt_button=ttk.Button(bar,text="Record synthetic receipt",command=confirm_receipt,state="disabled")
    receipt_button.pack(side="left",padx=4)
    asof_button=ttk.Button(bar,text="Evaluate as-of date",command=project,state="disabled")
    asof_button.pack(side="left",padx=4)
    cashflow_button=ttk.Button(window,text="Model cash flow and reserve",command=cashflow,state="disabled")
    cashflow_button.pack(pady=3)
    def projection_changed(*_):
        if workspace.record is not None:
            write("Model inputs changed. Evaluate as-of date or cash flow explicitly.")
            status.configure(text="Previous financial projection cleared.")
    asof.trace_add("write",projection_changed)
    reserve.trace_add("write",projection_changed)
    issue.trace_add("write",lambda *_:clear("Issue date changed; preview or refresh explicitly."))
    def check():
        nonlocal timer
        if blocked_check() is not False and (workspace.previewed is not None or workspace.record is not None):
            clear("Halted or busy; refresh after resume.")
        timer=window.after(100,check)
    def destroyed(event):
        if event.widget is window and timer is not None:
            window.after_cancel(timer)
            workspace.clear()
    window.bind("<Destroy>",destroyed,add="+")
    check()
    if smoke:
        date=obligation["notes"][-1]["recorded_at"][:10]
        issue.set(date); asof.set(date); paid.set(date)
        inv=preview()
        saved=create(True)
        if inv is None or saved is None or saved["invoice"]!=inv:
            raise RuntimeError("native finance preview/create failed")
        reference.set("SIM-GUIFIRST"); amount.set("0.01")
        part=receive(True)
        if part is None or part["state"]!="SIMULATED_PARTIAL":
            raise RuntimeError("native finance partial receipt failed")
        asof.set((_date(inv["due_date"])+timedelta(days=1)).isoformat())
        project()
        if workspace.projection(asof.get())["simulated_overdue_cents"]!=inv["gross_cents"]-1:
            raise RuntimeError("native finance aging failed")
        reference.set("SIM-GUIFINAL")
        rest=inv["gross_cents"]-1
        amount.set(f"{rest//100}.{rest%100:02d}")
        final=receive(True)
        if final is None or final["state"]!="SIMULATED_SETTLED" or final["payment_received"]:
            raise RuntimeError("native finance settlement failed")
        if refresh()!=final or "SIMULATION ONLY" not in output.get("1.0","end"):
            raise RuntimeError("native finance persistence failed")
        reserve.set("5000")
        result=cashflow()
        if (result is None or result["allocation_modeled"] is not True
                or result["modeled_total_cost_cents"]!=0
                or result["modeled_protected_reserve_cents"]+result["modeled_reinvestment_cents"]!=inv["gross_cents"]
                or result["funds_available"] or result["reinvestment_authorized"]
                or "Hypothetical protected reserve" not in output.get("1.0","end")):
            raise RuntimeError("native modeled allocation failed")
    return window
