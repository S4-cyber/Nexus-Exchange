"""Local hypothetical invoices and synthetic receipt reconciliation only.

No tax invoice, real receivable, accounting entry, customer or bank integration.
All monetary values are exact integer USD cents; plans are alternative models.
"""
from contextlib import contextmanager
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import sqlite3

from .checklist_store import _hash
from .digital_deliverable import _permit
from .deliverable_obligations import _FLAGS_EXTRA, _stored_stamp, _stamp
from .lead_store import _digest, _json, _now
from .obligation_workspace import validate_record
from .scenario_store import _inputs
from .scout import _timestamp

FORMAT="nexus-simulated-invoice-v1"
MAX_CENTS=99_999_999_999_999
MAX_INVOICES=10000
MAX_RECEIPTS=64
MAX_PAYLOAD=8192
_FLAGS=tuple(dict.fromkeys((*_FLAGS_EXTRA,"invoice_issued","real_receivable",
                           "actual_balance_verified","funds_available","reinvestment_authorized")))
_SCOPE_FIELDS={"plan_id","obligation_id","obligation_head_sha256",
               "contract_sha256","qa_report_sha256","artifact_sha256","scenario_sha256"}
_INVOICE_FIELDS={"format","mode","currency","gross_cents","payment_days",
                 "issue_date","due_date","invoice_id",*_SCOPE_FIELDS,*_FLAGS}
_EVENT_FIELDS={"invoice_id","sequence","previous_sha256","sim_reference",
               "amount_cents","paid_on","recorded_at"}


def _shape(raw,keys):
    if type(raw) is not dict or set(raw)!=set(keys):
        raise ValueError("invalid exact simulated invoice schema")


def _date(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",value):
        raise ValueError("canonical simulation calendar date required")
    result=date.fromisoformat(value)
    if result.year<1900:
        raise ValueError("simulation date outside supported range")
    return result


def _due(issued,days):
    if type(days) is not int or not 0<=days<=3650:
        raise ValueError("known modeled payment terms required")
    try:
        return (_date(issued)+timedelta(days=days)).isoformat()
    except OverflowError:
        raise ValueError("simulation due date outside supported range") from None


def _positive_cents(value):
    if type(value) is not int or not 1<=value<=MAX_CENTS:
        raise ValueError("positive bounded USD cents required")
    return value


def _cents(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,2})?",value):
        raise ValueError("known positive modeled USD amount required")
    whole,_,fraction=value.partition(".")
    return _positive_cents(int(whole)*100+int(fraction.ljust(2,"0") or "0"))


def _reference(value):
    if type(value) is not str or not re.fullmatch(r"SIM-[A-Z0-9]{1,32}",value):
        raise ValueError("synthetic SIM- receipt reference required")
    return value


def _validate_invoice(raw):
    _shape(raw,_INVOICE_FIELDS)
    if (raw["format"]!=FORMAT or raw["mode"]!="SIMULATION_ONLY"
            or raw["currency"]!="USD" or any(raw[k] is not False for k in _FLAGS)):
        raise ValueError("simulated invoice authority or format mismatch")
    for field in _SCOPE_FIELDS:
        _hash(raw[field])
    _positive_cents(raw["gross_cents"])
    if raw["due_date"]!=_due(raw["issue_date"],raw["payment_days"]):
        raise ValueError("simulated due date mismatch")
    payload={k:v for k,v in raw.items() if k!="invoice_id"}
    if _digest(_json(payload))!=_hash(raw["invoice_id"]):
        raise ValueError("simulated invoice identity mismatch")
    return raw


def build_invoice(obligation,saved,*,issue_date,now,halted=None,halt_check=None):
    """Pin one historical artifact and the entire immutable modeled compensation."""
    _permit(halted,halt_check)
    now=_now(now)
    if type(saved) is not dict:
        raise ValueError("saved scenario unavailable")
    plan_id=_hash(saved.get("plan_id"))
    record=validate_record(obligation,plan_id)
    notes=record["notes"]
    if not notes or notes[-1]["kind"]!="acceptance_claim_noted":
        raise ValueError("latest local acceptance claim evidence note required for simulation")
    # A note is a declaration, not verified acceptance. The model assumes
    # delivery/acceptance on the explicit simulated issue date, not actual dates.
    if (_timestamp(notes[-1]["recorded_at"])>now or
            _date(issue_date)<_timestamp(notes[-1]["recorded_at"]).date()):
        raise ValueError("simulation issue date precedes recorded evidence")
    inputs=_inputs(saved["context"],saved["scenario"],saved["plan"])
    if (_digest(_json(inputs))!=plan_id or
            any(saved.get(k) is not False for k in
                ("independently_verified","execution_eligible","external_authority","genesis_verified"))):
        raise ValueError("saved scenario identity mismatch")
    contract=record["binding"]["contract"]
    qa=record["binding"]["qa_report"]
    scenario=inputs["scenario"]
    digest=_digest(_json(dict(context=inputs["context"],scenario=scenario)))
    if (contract["context"]!=inputs["context"] or contract["scenario_sha256"]!=digest
            or _timestamp(saved["created_at"])>_timestamp(record["created_at"])):
        raise ValueError("obligation and modeled compensation scope mismatch")
    payload=dict(format=FORMAT,mode="SIMULATION_ONLY",currency="USD",
        plan_id=plan_id,obligation_id=record["obligation_id"],
        obligation_head_sha256=record["head_sha256"],contract_sha256=contract["contract_sha256"],
        qa_report_sha256=qa["report_sha256"],artifact_sha256=qa["artifact_sha256"],
        scenario_sha256=digest,gross_cents=_cents(scenario["compensation"]),
        payment_days=scenario["payment_days_after_delivery"],issue_date=issue_date,
        due_date=_due(issue_date,scenario["payment_days_after_delivery"]),
        **dict.fromkeys(_FLAGS,False))
    invoice=dict(payload,invoice_id=_digest(_json(payload)))
    _validate_invoice(invoice)
    _permit(halted,halt_check)
    return invoice


def _decode(payload,digest):
    if type(payload) is not str or len(payload)>MAX_PAYLOAD or _digest(payload)!=digest:
        raise ValueError("simulated ledger integrity mismatch")
    data=json.loads(payload)
    if _json(data)!=payload:
        raise ValueError("noncanonical simulated ledger payload")
    return data


class InvoiceStore:
    """One simulated invoice per saved plan and obligation; no real balances."""
    def __init__(self,path,*,existing_only=False):
        if path!=":memory:":
            path=Path(path)
            if os.path.lexists(path) and (path.is_symlink() or not path.is_file()):
                raise ValueError("invalid simulated ledger path")
            if existing_only and not path.is_file():
                raise ValueError("simulated ledger missing")
        self.db=sqlite3.connect(path,timeout=5,isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            if existing_only:
                tables={row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"sim_invoices_v1","sim_receipts_v1"}<=tables:
                    raise ValueError("simulated ledger schema missing")
            else:
                self.db.execute("""CREATE TABLE IF NOT EXISTS sim_invoices_v1(
                    invoice_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL UNIQUE,
                    obligation_id TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,digest TEXT NOT NULL)""")
                self.db.execute("""CREATE TABLE IF NOT EXISTS sim_receipts_v1(
                    invoice_id TEXT NOT NULL,sequence INTEGER NOT NULL,sim_reference TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(invoice_id,sequence),
                    FOREIGN KEY(invoice_id) REFERENCES sim_invoices_v1(invoice_id))""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.db.close()

    @contextmanager
    def _transaction(self,*,write,halted,halt_check):
        _permit(halted,halt_check)
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            _permit(halted,halt_check)
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def _guard_write(self):
        """Reject unexpected schema objects before a durable simulation write."""
        for table in ("sim_invoices_v1", "sim_receipts_v1"):
            if self.db.execute("SELECT type FROM main.sqlite_master WHERE name=? COLLATE NOCASE",
                               (table,)).fetchone()!=("table",):
                raise ValueError("simulated ledger table missing")
            if self.db.execute("SELECT 1 FROM sqlite_temp_master WHERE name=? COLLATE NOCASE "
                               "AND type IN ('table','view') LIMIT 1",(table,)).fetchone() is not None:
                raise ValueError("unexpected simulated ledger shadow")
            for catalog in ("main.sqlite_master","sqlite_temp_master"):
                if self.db.execute("SELECT 1 FROM "+catalog+" WHERE type='trigger' "
                                   "AND tbl_name=? COLLATE NOCASE LIMIT 1",(table,)).fetchone() is not None:
                    raise ValueError("unexpected simulated ledger trigger")

    def _read(self,plan_id,key,now):
        _hash(plan_id)
        _hash(key)
        row=self.db.execute("""SELECT invoice_id,plan_id,obligation_id,created_at,payload,digest
            FROM main.sim_invoices_v1 WHERE invoice_id=?""",(key,)).fetchone()
        if row is None or row[1]!=plan_id:
            raise ValueError("simulated invoice unavailable or outside selected plan")
        data=_decode(row[4],row[5])
        _shape(data,{"invoice","created_at"})
        invoice=_validate_invoice(data["invoice"])
        created=_stored_stamp(data["created_at"])
        prior_time=_timestamp(created)
        if ((invoice["invoice_id"],invoice["plan_id"],invoice["obligation_id"],created)!=row[:4]
                or prior_time>now):
            raise ValueError("simulated invoice stored identity mismatch")
        rows=self.db.execute("""SELECT sequence,sim_reference,payload,digest FROM main.sim_receipts_v1
            WHERE invoice_id=? ORDER BY sequence LIMIT ?""",(key,MAX_RECEIPTS+1)).fetchall()
        if len(rows)>MAX_RECEIPTS:
            raise ValueError("simulated receipt capacity exceeded")
        head=row[5]
        paid=0
        prior_date=_date(invoice["issue_date"])
        seen=set()
        events=[]
        for sequence,(seq,reference,payload,digest) in enumerate(rows,1):
            event=_decode(payload,digest)
            _shape(event,_EVENT_FIELDS)
            current_date=_date(event["paid_on"])
            current_time=_timestamp(_stored_stamp(event["recorded_at"]))
            ref=_reference(event["sim_reference"])
            amount=_positive_cents(event["amount_cents"])
            if (type(seq) is not int or seq!=sequence or type(event["sequence"]) is not int
                    or event["sequence"]!=sequence or ref!=reference or ref in seen
                    or event["invoice_id"]!=key or event["previous_sha256"]!=head
                    or current_date<prior_date or not prior_time<=current_time<=now):
                raise ValueError("simulated receipt chain mismatch")
            paid+=amount
            if paid>invoice["gross_cents"]:
                raise ValueError("stored simulated overpayment")
            events.append(dict(event,event_sha256=digest))
            seen.add(ref)
            head=digest
            prior_date=current_date
            prior_time=current_time
        remaining=invoice["gross_cents"]-paid
        return dict(invoice=invoice,created_at=created,registration_sha256=row[5],
                    head_sha256=head,receipts=events,simulated_received_cents=paid,
                    simulated_outstanding_cents=remaining,
                    state=("SIMULATED_SETTLED" if not remaining else
                           "SIMULATED_PARTIAL" if paid else "SIMULATED_UNPAID"),
                    historical_only=True,**dict.fromkeys(_FLAGS,False))

    def create(self,invoice,*,now,confirmed=None,halted=None,halt_check=None):
        _permit(halted,halt_check)
        if confirmed is not True:
            raise PermissionError("explicit simulated invoice confirmation required")
        now=_now(now)
        invoice=_validate_invoice(invoice)
        key,plan=invoice["invoice_id"],invoice["plan_id"]
        with self._transaction(write=True,halted=halted,halt_check=halt_check):
            self._guard_write()
            prior=self.db.execute("SELECT invoice_id FROM main.sim_invoices_v1 WHERE plan_id=?",(plan,)).fetchone()
            if prior is not None:
                if prior[0]!=key:
                    raise ValueError("one simulated invoice per saved plan; alternate issue requires review")
                result=self._read(plan,key,now)
                if _json(result["invoice"])!=_json(invoice):
                    raise ValueError("conflicting simulated invoice identity")
                return result
            if self.db.execute("SELECT 1 FROM main.sim_invoices_v1 WHERE obligation_id=?",
                               (invoice["obligation_id"],)).fetchone() is not None:
                raise ValueError("obligation already assigned a simulated invoice")
            if self.db.execute("SELECT COUNT(*) FROM main.sim_invoices_v1").fetchone()[0]>=MAX_INVOICES:
                raise ValueError("simulated invoice capacity review required")
            created=_stamp(now)
            payload=_json(dict(invoice=invoice,created_at=created))
            digest=_digest(payload)
            changed=self.db.execute("INSERT INTO main.sim_invoices_v1 VALUES (?,?,?,?,?,?)",
                (key,plan,invoice["obligation_id"],created,payload,digest))
            if changed.rowcount!=1:
                raise ValueError("simulated invoice publication mismatch")
            result=self._read(plan,key,now)
            if (result["invoice"]!=invoice or result["created_at"]!=created
                    or result["head_sha256"]!=digest or result["registration_sha256"]!=digest
                    or result["receipts"] or result["simulated_received_cents"]!=0
                    or result["simulated_outstanding_cents"]!=invoice["gross_cents"]):
                raise ValueError("simulated invoice publication mismatch")
            return result

    def history(self,plan_id,key,*,now,halted=None,halt_check=None):
        now=_now(now)
        with self._transaction(write=False,halted=halted,halt_check=halt_check):
            return self._read(plan_id,key,now)

    def find(self,plan_id,*,now,halted=None,halt_check=None):
        _hash(plan_id)
        now=_now(now)
        with self._transaction(write=False,halted=halted,halt_check=halt_check):
            row=self.db.execute("SELECT invoice_id FROM main.sim_invoices_v1 WHERE plan_id=?",(plan_id,)).fetchone()
            return None if row is None else self._read(plan_id,row[0],now)

    def payment(self,plan_id,key,*,expected_head,sim_reference,amount,paid_on,now,
                confirmed=None,halted=None,halt_check=None):
        _permit(halted,halt_check)
        if confirmed is not True:
            raise PermissionError("explicit synthetic receipt confirmation required")
        _hash(expected_head)
        ref=_reference(sim_reference)
        cents=_cents(amount)
        paid_date=_date(paid_on)
        now=_now(now)
        with self._transaction(write=True,halted=halted,halt_check=halt_check):
            self._guard_write()
            record=self._read(plan_id,key,now)
            if record["head_sha256"]!=expected_head:
                raise ValueError("simulated invoice changed; inspect again")
            if self.db.execute("SELECT 1 FROM main.sim_receipts_v1 WHERE sim_reference=?",(ref,)).fetchone() is not None:
                raise ValueError("duplicate synthetic receipt reference")
            if cents>record["simulated_outstanding_cents"]:
                raise ValueError("simulated overpayment or already settled")
            events=record["receipts"]
            if len(events)>=MAX_RECEIPTS:
                raise ValueError("simulated receipt capacity review required")
            previous_date=events[-1]["paid_on"] if events else record["invoice"]["issue_date"]
            if paid_date<_date(previous_date):
                raise ValueError("synthetic receipt date regression")
            event=dict(invoice_id=key,sequence=len(events)+1,previous_sha256=expected_head,
                       sim_reference=ref,amount_cents=cents,paid_on=paid_on,recorded_at=_stamp(now))
            payload=_json(event)
            digest=_digest(payload)
            changed=self.db.execute("INSERT INTO main.sim_receipts_v1 VALUES (?,?,?,?,?)",
                (key,event["sequence"],ref,payload,digest))
            if changed.rowcount!=1:
                raise ValueError("simulated receipt publication mismatch")
            result=self._read(plan_id,key,now)
            if (result["invoice"]!=record["invoice"] or result["created_at"]!=record["created_at"]
                    or result["registration_sha256"]!=record["registration_sha256"]
                    or result["receipts"]!=events+[dict(event,event_sha256=digest)]
                    or result["head_sha256"]!=digest
                    or result["simulated_received_cents"]!=record["simulated_received_cents"]+cents
                    or result["simulated_outstanding_cents"]!=record["simulated_outstanding_cents"]-cents):
                raise ValueError("simulated receipt publication mismatch")
            return result
