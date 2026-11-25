"""Deterministic local CSV work sample, not a contract or buyer acceptance.

Untrusted cells are data, never instructions, formulas, code or paths.
No file I/O, network, model API, invoice, or commercial dispatch occurs.
"""
import csv
from hashlib import sha256
import io
import re
import unicodedata

from .checklist_store import _context, _hash
from .council_audit import validate_snapshot
from .governor import Action, decide
from .lead_store import _digest, _json

FORMAT="nexus-csv-deliverable-contract-v1"
REPORT="nexus-csv-deliverable-report-v1"
MAX_INPUT_BYTES=256*1024
MAX_OUTPUT_BYTES=512*1024
MAX_ROWS=2000
MAX_COLUMNS=16
MAX_CELL_CHARS=256
_FLAGS=("independently_verified","buyer_accepted","contract_awarded",
        "invoice_eligible","revenue_realized","zero_capital_verified",
        "execution_eligible","external_authority","dispatch_enabled")
_SPEC={"input_sha256","columns","key_column","expected_rows"}
_CONTRACT={"format","plan_id","context","scenario_sha256","schedule_sha256",
           "specification","contract_sha256",*_FLAGS}


class DeliverableError(ValueError):
    """Fixed local reason code; no source cell or input path in errors."""


def _permit(halted,halt_check=None):
    live=halt_check() if callable(halt_check) else False if halt_check is None else None
    if (not decide(Action.SIMULATE,halted=halted).allowed or live is not False):
        raise PermissionError("HALTED_OR_UNKNOWN")


def _shape(value,fields):
    if type(value) is not dict or set(value)!=fields:
        raise DeliverableError("INVALID_DELIVERABLE_SCHEMA")


def _spec(raw):
    _shape(raw,_SPEC)
    cols=raw["columns"]
    if (type(cols) is not list or not 1<=len(cols)<=MAX_COLUMNS or
            any(type(col) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}",col)
                for col in cols) or len(set(cols))!=len(cols)):
        raise DeliverableError("INVALID_COLUMN_SCHEMA")
    key=raw["key_column"]
    if type(key) is not str or key not in cols:
        raise DeliverableError("INVALID_KEY_COLUMN")
    n=raw["expected_rows"]
    if type(n) is not int or not 1<=n<=MAX_ROWS:
        raise DeliverableError("INVALID_EXPECTED_ROW_COUNT")
    return dict(input_sha256=_hash(raw["input_sha256"]),columns=list(cols),
                key_column=key,expected_rows=n)


def build_contract(snapshot,specification,*,halted=None):
    """Bind explicit work-sample requirements to one current local saved-plan view."""
    _permit(halted)
    snap=validate_snapshot(snapshot)
    if snap["source_hold"] is not None:
        raise DeliverableError("CURRENT_SOURCE_REVIEW_REQUIRED")
    spec=_spec(specification)
    payload=dict(format=FORMAT,plan_id=snap["plan_id"],context=dict(snap["context"]),
                 scenario_sha256=snap["scenario_sha256"],schedule_sha256=snap["schedule_sha256"],
                 specification=spec,**dict.fromkeys(_FLAGS,False))
    return dict(payload,contract_sha256=_digest(_json(payload)))


def _contract(raw):
    _shape(raw,_CONTRACT)
    ctx=_context(raw["context"])
    if ctx["profile_revision"] is None:
        raise DeliverableError("CURRENT_DECLARED_PROFILE_REQUIRED")
    if raw["format"]!=FORMAT or any(raw[k] is not False for k in _FLAGS):
        raise DeliverableError("DELIVERABLE_AUTHORITY_OR_SCOPE_MISMATCH")
    payload=dict(format=FORMAT,plan_id=_hash(raw["plan_id"]),context=ctx,
                 scenario_sha256=_hash(raw["scenario_sha256"]),
                 schedule_sha256=_hash(raw["schedule_sha256"]),
                 specification=_spec(raw["specification"]),**dict.fromkeys(_FLAGS,False))
    expected=dict(payload,contract_sha256=_digest(_json(payload)))
    if _json(raw)!=_json(expected):
        raise DeliverableError("DELIVERABLE_CONTRACT_INTEGRITY")
    return expected


def _cell(value):
    if (len(value)>MAX_CELL_CHARS or
            any(unicodedata.category(c).startswith("C") for c in value)):
        raise DeliverableError("INVALID_CELL")
    # Conservative: reject formula-shaped cells rather than modify data.
    # NFKC check includes fullwidth compatibility forms; leading spaces do not
    # bypass the check. Negative number strings are intentionally rejected.
    probe=unicodedata.normalize("NFKC",value).lstrip()
    if probe.startswith(("=","+","-","@")):
        raise DeliverableError("FORMULA_SHAPED_CELL")
    return value


def _table(raw,spec,*,maximum,ordered,halted,halt_check):
    _permit(halted,halt_check)
    if type(raw) is not bytes or not 1<=len(raw)<=maximum:
        raise DeliverableError("CSV_BYTE_LIMIT")
    try:
        reader=csv.reader(io.StringIO(raw.decode("utf-8"),newline=""),strict=True)
        header=next(reader)
        cols=spec["columns"]
        if (len(header)!=len(cols) or set(header)!=set(cols) or
                (ordered and header!=cols)):
            raise DeliverableError("CSV_HEADER_MISMATCH")
        indexes=[header.index(col) for col in cols]
        key_index=cols.index(spec["key_column"])
        rows={}
        observed=[]
        for row in reader:
            _permit(halted,halt_check)
            if len(rows)>=MAX_ROWS or len(row)!=len(cols):
                raise DeliverableError("CSV_ROW_LIMIT_OR_WIDTH")
            values=tuple(_cell(row[i]) for i in indexes)
            key=values[key_index]
            if not key or key!=key.strip() or key in rows:
                raise DeliverableError("CSV_KEY_EMPTY_OR_DUPLICATE")
            rows[key]=values
            observed.append(key)
        if len(rows)!=spec["expected_rows"]:
            raise DeliverableError("CSV_ROW_COUNT_MISMATCH")
        if ordered and observed!=sorted(observed):
            raise DeliverableError("CSV_SORT_ORDER_MISMATCH")
        _permit(halted,halt_check)
        return rows
    except (UnicodeError,csv.Error,StopIteration):
        raise DeliverableError("CSV_PARSE_INVALID") from None


def _input(contract,raw,halted,halt_check):
    spec=contract["specification"]
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_INPUT_BYTES:
        raise DeliverableError("CSV_BYTE_LIMIT")
    if sha256(raw).hexdigest()!=spec["input_sha256"]:
        raise DeliverableError("CSV_INPUT_FINGERPRINT_MISMATCH")
    return _table(raw,spec,maximum=MAX_INPUT_BYTES,ordered=False,
                  halted=halted,halt_check=halt_check)


def verify_csv(contract,raw,artifact,*,halted=None,halt_check=None):
    """Reparse both byte streams and check every field by exact unique key.

    Verification is a local mechanical comparison to supplied bytes and
    declared requirements, not independent authentication or buyer acceptance.
    """
    _permit(halted,halt_check)
    checked=_contract(contract)
    spec=checked["specification"]
    original=_input(checked,raw,halted,halt_check)
    output=_table(artifact,spec,maximum=MAX_OUTPUT_BYTES,ordered=True,
                  halted=halted,halt_check=halt_check)
    if original!=output:
        raise DeliverableError("CSV_CONTENT_MISMATCH")
    # Compare canonical serialization as well: noncanonical output bytes fail.
    if artifact!=_serialize(spec,output,halted,halt_check):
        raise DeliverableError("CSV_CANONICAL_OUTPUT_REQUIRED")
    result=dict(format=REPORT,contract_sha256=checked["contract_sha256"],
                plan_id=checked["plan_id"],input_sha256=sha256(raw).hexdigest(),
                artifact_sha256=sha256(artifact).hexdigest(),
                input_bytes=len(raw),artifact_bytes=len(artifact),rows=len(output),
                columns=list(spec["columns"]),key_column=spec["key_column"],
                checks=["EXACT_INPUT_PIN","COLUMN_SCHEMA","EXPECTED_ROW_COUNT",
                        "UNIQUE_KEYS","NO_FORMULA_SHAPED_CELLS","EXACT_CELL_PRESERVATION",
                        "CANONICAL_ORDER_AND_SERIALIZATION"],
                local_criteria_passed=True,**dict.fromkeys(_FLAGS,False))
    _permit(halted,halt_check)
    return dict(result,report_sha256=_digest(_json(result)))


def _serialize(spec,rows,halted,halt_check):
    buffer=io.StringIO(newline="")
    writer=csv.writer(buffer,lineterminator="\r\n",quoting=csv.QUOTE_ALL)
    writer.writerow(spec["columns"])
    for key in sorted(rows):
        _permit(halted,halt_check)
        writer.writerow(rows[key])
        # Bound intermediate characters; final UTF-8 byte cap checked below.
        if buffer.tell()>MAX_OUTPUT_BYTES:
            raise DeliverableError("CSV_OUTPUT_LIMIT")
    artifact=buffer.getvalue().encode("utf-8")
    if len(artifact)>MAX_OUTPUT_BYTES:
        raise DeliverableError("CSV_OUTPUT_LIMIT")
    return artifact


def produce_csv(contract,raw,*,halted=None,halt_check=None):
    """Produce actual UTF-8 CSV bytes, plus a separate deterministic QA report."""
    _permit(halted,halt_check)
    checked=_contract(contract)
    rows=_input(checked,raw,halted,halt_check)
    artifact=_serialize(checked["specification"],rows,halted,halt_check)
    report=verify_csv(checked,raw,artifact,halted=halted,halt_check=halt_check)
    _permit(halted,halt_check)
    return dict(contract=checked,artifact=artifact,report=report)
