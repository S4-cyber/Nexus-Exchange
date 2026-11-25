"""Deterministic local CSV work sample, not a contract or buyer acceptance.

Untrusted cells are data, never instructions, formulas, code or paths.
No file I/O, network, model API, invoice, or commercial dispatch occurs.
"""
import csv
from hashlib import sha256
import io
import json
import re
import unicodedata

from .checklist_store import _context, _hash
from .council_audit import validate_snapshot
from .governor import Action, decide
from .lead_store import _digest, _json

FORMAT="nexus-csv-deliverable-contract-v2"
JSON_FORMAT="nexus-json-records-to-csv-contract-v1"
PROFILE_FORMAT="nexus-csv-column-profile-contract-v1"
RECONCILE_FORMAT="nexus-csv-key-reconciliation-contract-v1"
RECONCILE_REPORT="nexus-csv-reconciliation-report-v1"
PROFILE_COLUMNS=("column","row_count","empty_count","whitespace_only_count",
                 "nonblank_count","distinct_nonblank_count","min_chars","max_chars")
CSV_SOURCE="UTF8_CSV"
JSON_SOURCE="UTF8_JSON_RECORDS"
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
_CONTRACT={"format","plan_id","context","scenario_sha256","schedule_scope_sha256",
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


def _spec(raw,*,reconcile=False):
    _shape(raw,_SPEC|{"right_input_sha256","right_expected_rows"} if reconcile else _SPEC)
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
    result=dict(input_sha256=_hash(raw["input_sha256"]),columns=list(cols),
                key_column=key,expected_rows=n)
    if reconcile:
        right=raw["right_expected_rows"]
        if type(right) is not int or not 1<=right<=MAX_ROWS or n+right>MAX_ROWS:
            raise DeliverableError("RECONCILIATION_COMBINED_ROW_LIMIT")
        result.update(right_input_sha256=_hash(raw["right_input_sha256"]),right_expected_rows=right)
    return result


def _schedule_scope(plan_id,context,scenario_sha256):
    # The archive plan ID is content-addressed over context, financial inputs
    # and delivery-plan inputs. The Council schedule evaluation digest is
    # time-dependent; it must never serve as an immutable work-sample identity.
    return _digest(_json(dict(namespace="saved-plan-schedule-scope-v1",
        plan_id=_hash(plan_id),context=_context(context),
        scenario_sha256=_hash(scenario_sha256))))


def _source_contract_format(source_format,operation="PRESERVE"):
    if type(source_format) is not str or source_format not in (CSV_SOURCE,JSON_SOURCE):
        raise DeliverableError("UNSUPPORTED_SOURCE_FORMAT")
    if type(operation) is not str or operation not in ("PRESERVE","COLUMN_PROFILE","RECONCILE"):
        raise DeliverableError("UNSUPPORTED_DELIVERABLE_OPERATION")
    if operation in ("COLUMN_PROFILE","RECONCILE"):
        if source_format!=CSV_SOURCE:
            raise DeliverableError("UNSUPPORTED_SERVICE_SOURCE")
        return PROFILE_FORMAT if operation=="COLUMN_PROFILE" else RECONCILE_FORMAT
    return FORMAT if source_format==CSV_SOURCE else JSON_FORMAT


def build_contract(snapshot,specification,*,halted=None,source_format=CSV_SOURCE,operation="PRESERVE"):
    """Bind explicit work-sample requirements to one current local saved-plan view."""
    _permit(halted)
    snap=validate_snapshot(snapshot)
    if snap["source_hold"] is not None:
        raise DeliverableError("CURRENT_SOURCE_REVIEW_REQUIRED")
    format_id=_source_contract_format(source_format,operation)
    spec=_spec(specification,reconcile=format_id==RECONCILE_FORMAT)
    payload=dict(format=format_id,plan_id=snap["plan_id"],context=dict(snap["context"]),
                 scenario_sha256=snap["scenario_sha256"],
                 schedule_scope_sha256=_schedule_scope(snap["plan_id"],snap["context"],snap["scenario_sha256"]),
                 specification=spec,**dict.fromkeys(_FLAGS,False))
    return dict(payload,contract_sha256=_digest(_json(payload)))


def _contract(raw):
    _shape(raw,_CONTRACT)
    ctx=_context(raw["context"])
    if ctx["profile_revision"] is None:
        raise DeliverableError("CURRENT_DECLARED_PROFILE_REQUIRED")
    if raw["format"] not in (FORMAT,JSON_FORMAT,PROFILE_FORMAT,RECONCILE_FORMAT) or any(raw[k] is not False for k in _FLAGS):
        raise DeliverableError("DELIVERABLE_AUTHORITY_OR_SCOPE_MISMATCH")
    payload=dict(format=raw["format"],plan_id=_hash(raw["plan_id"]),context=ctx,
                 scenario_sha256=_hash(raw["scenario_sha256"]),
                 schedule_scope_sha256=_schedule_scope(raw["plan_id"],ctx,raw["scenario_sha256"]),
                 specification=_spec(raw["specification"],reconcile=raw["format"]==RECONCILE_FORMAT),**dict.fromkeys(_FLAGS,False))
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


def _string_records(raw, halted, halt_check):
    """Decode JSON without coercing values or silently dropping duplicate members."""
    _permit(halted,halt_check)
    def pairs(items):
        if len(items)>MAX_COLUMNS:
            raise DeliverableError("JSON_RECORD_SCHEMA_MISMATCH")
        record={}
        for key,value in items:
            if key in record:
                raise DeliverableError("JSON_DUPLICATE_MEMBER")
            if type(value) is not str:
                raise DeliverableError("JSON_NON_STRING_VALUE")
            record[key]=value
        return record
    def reject_number(_value):
        raise DeliverableError("JSON_NON_STRING_VALUE")
    try:
        records=json.loads(raw.decode("utf-8"),object_pairs_hook=pairs,
                           parse_int=reject_number,parse_float=reject_number,
                           parse_constant=reject_number)
    except (UnicodeError,json.JSONDecodeError,RecursionError):
        raise DeliverableError("JSON_PARSE_INVALID") from None
    _permit(halted,halt_check)
    return records


def _json_table(raw,spec,halted,halt_check):
    """Accept only a bounded array of flat, exact-schema string records."""
    records = _string_records(raw, halted, halt_check)
    if type(records) is not list or len(records)!=spec["expected_rows"]:
        raise DeliverableError("JSON_ROW_COUNT_OR_SHAPE_MISMATCH")
    cols=spec["columns"]
    key_index=cols.index(spec["key_column"])
    rows={}
    for record in records:
        _permit(halted,halt_check)
        if type(record) is not dict or set(record)!=set(cols):
            raise DeliverableError("JSON_RECORD_SCHEMA_MISMATCH")
        values=tuple(_cell(record[col]) for col in cols)
        key=values[key_index]
        if not key or key!=key.strip() or key in rows:
            raise DeliverableError("CSV_KEY_EMPTY_OR_DUPLICATE")
        rows[key]=values
    _permit(halted,halt_check)
    return rows


def _output_spec(contract,output_rows=None):
    spec=contract["specification"]
    if contract["format"]==PROFILE_FORMAT:
        return dict(spec,columns=list(PROFILE_COLUMNS),key_column="column",
                    expected_rows=len(spec["columns"]))
    if contract["format"]==RECONCILE_FORMAT:
        lo=max(spec["expected_rows"],spec["right_expected_rows"])
        hi=spec["expected_rows"]+spec["right_expected_rows"]
        if type(output_rows) is not int or not lo<=output_rows<=hi:
            raise DeliverableError("RECONCILIATION_OUTPUT_ROW_COUNT")
        return dict(spec,columns=["record_key","status","changed_field_count",
                    *("changed_"+col for col in spec["columns"] if col!=spec["key_column"])],
                    key_column="record_key",expected_rows=output_rows)
    return spec


def _reconcile_rows(spec,left,right,halted,halt_check):
    """Report keys and exact changed-column flags; never include non-key values."""
    indexes=[i for i,col in enumerate(spec["columns"]) if col!=spec["key_column"]]
    result={}
    for key in left.keys()|right.keys():
        _permit(halted,halt_check)
        if key not in right or key not in left:
            state="LEFT_ONLY" if key in left else "RIGHT_ONLY"
            result[key]=(key,state,"0",*("NOT_COMPARED" for _ in indexes))
            continue
        flags=tuple("YES" if left[key][i]!=right[key][i] else "NO" for i in indexes)
        count=flags.count("YES")
        result[key]=(key,"CHANGED" if count else "UNCHANGED",str(count),*flags)
    return result


def _verify_reconciliation(spec,left,right,output,halted,halt_check):
    """Recompute membership, changes, and all flags separately from production."""
    if set(output)!=set(left)|set(right):
        raise DeliverableError("RECONCILIATION_KEY_SET_MISMATCH")
    for key,row in output.items():
        _permit(halted,halt_check)
        if key in left and key in right:
            different={col for col,a,b in zip(spec["columns"],left[key],right[key]) if a!=b}
            expected=(key,"CHANGED" if different else "UNCHANGED",str(len(different)),
                      *("YES" if col in different else "NO" for col in spec["columns"] if col!=spec["key_column"]))
        else:
            expected=(key,"LEFT_ONLY" if key in left else "RIGHT_ONLY","0",
                      *("NOT_COMPARED" for col in spec["columns"] if col!=spec["key_column"]))
        if row!=expected:
            raise DeliverableError("RECONCILIATION_DISCREPANCY_MISMATCH")
    _permit(halted,halt_check)


def _right_input(contract,right_raw,halted,halt_check):
    _permit(halted,halt_check)
    if contract["format"]!=RECONCILE_FORMAT:
        if right_raw is not None:
            raise DeliverableError("UNEXPECTED_SECOND_INPUT")
        return None
    spec=contract["specification"]
    if type(right_raw) is not bytes or not 1<=len(right_raw)<=MAX_INPUT_BYTES:
        raise DeliverableError("CSV_BYTE_LIMIT")
    if sha256(right_raw).hexdigest()!=spec["right_input_sha256"]:
        raise DeliverableError("RIGHT_INPUT_FINGERPRINT_MISMATCH")
    return _table(right_raw,dict(spec,expected_rows=spec["right_expected_rows"]),
                  maximum=MAX_INPUT_BYTES,ordered=False,halted=halted,halt_check=halt_check)


def _profile_rows(spec,rows,halted,halt_check):
    """Aggregate only: never emit a source cell value in the report."""
    stats={col:dict(empty=0,whitespace=0,nonblank=0,distinct=set(),
                    low=MAX_CELL_CHARS,high=0) for col in spec["columns"]}
    for row in rows.values():
        _permit(halted,halt_check)
        for col,value in zip(spec["columns"],row):
            item=stats[col]
            if not value:
                item["empty"]+=1
            elif not value.strip():
                item["whitespace"]+=1
            else:
                item["nonblank"]+=1
                item["distinct"].add(value)
            item["low"]=min(item["low"],len(value))
            item["high"]=max(item["high"],len(value))
    _permit(halted,halt_check)
    return {col:(col,str(len(rows)),str(item["empty"]),str(item["whitespace"]),
                 str(item["nonblank"]),str(len(item["distinct"])),
                 str(item["low"]),str(item["high"])) for col,item in stats.items()}


def _verify_profile(spec,original,output,halted,halt_check):
    """Recompute per-column metrics separately from the producer's counters."""
    for index,col in enumerate(spec["columns"]):
        _permit(halted,halt_check)
        values=[row[index] for row in original.values()]
        nonblank=[value for value in values if value.strip()]
        expected=(col,str(len(values)),str(values.count("")),
                  str(sum(bool(value) and not value.strip() for value in values)),
                  str(len(nonblank)),str(len(set(nonblank))),
                  str(min(map(len,values))),str(max(map(len,values))))
        if output.get(col)!=expected:
            raise DeliverableError("CSV_PROFILE_METRIC_MISMATCH")
    _permit(halted,halt_check)


def _checks(contract):
    if contract["format"]==RECONCILE_FORMAT:
        return ["EXACT_BOTH_INPUT_PINS","BOTH_INPUT_COLUMN_SCHEMAS","EXPECTED_BOTH_INPUT_ROW_COUNTS",
                "BOTH_INPUT_UNIQUE_KEYS","NO_FORMULA_SHAPED_CELLS","EXACT_UNION_OF_KEYS",
                "EXACT_RECORD_STATUS","EXACT_CHANGED_FIELD_FLAGS","CANONICAL_ORDER_AND_SERIALIZATION"]
    if contract["format"]==PROFILE_FORMAT:
        return ["EXACT_INPUT_PIN","INPUT_COLUMN_SCHEMA","EXPECTED_INPUT_ROW_COUNT",
                "INPUT_UNIQUE_KEYS","NO_FORMULA_SHAPED_CELLS","EXACT_COLUMN_COUNTS",
                "EXACT_DISTINCT_NONBLANK_COUNTS","EXACT_LENGTH_RANGE",
                "CANONICAL_ORDER_AND_SERIALIZATION"]
    checks=["EXACT_INPUT_PIN","COLUMN_SCHEMA","EXPECTED_ROW_COUNT","UNIQUE_KEYS",
            "NO_FORMULA_SHAPED_CELLS","EXACT_CELL_PRESERVATION",
            "CANONICAL_ORDER_AND_SERIALIZATION"]
    if contract["format"]==JSON_FORMAT:
        checks.extend(["EXACT_JSON_RECORD_SCHEMA","STRING_VALUES_ONLY","NO_DUPLICATE_JSON_MEMBERS"])
    return checks


def _input(contract,raw,halted,halt_check):
    spec=contract["specification"]
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_INPUT_BYTES:
        raise DeliverableError("CSV_BYTE_LIMIT")
    if sha256(raw).hexdigest()!=spec["input_sha256"]:
        raise DeliverableError("CSV_INPUT_FINGERPRINT_MISMATCH")
    if contract["format"]==JSON_FORMAT:
        return _json_table(raw,spec,halted,halt_check)
    return _table(raw,spec,maximum=MAX_INPUT_BYTES,ordered=False,
                  halted=halted,halt_check=halt_check)


def verify_csv(contract,raw,artifact,*,halted=None,halt_check=None,right_raw=None):
    """Reparse both byte streams and check every field by exact unique key.

    Verification is a local mechanical comparison to supplied bytes and
    declared requirements, not independent authentication or buyer acceptance.
    """
    _permit(halted,halt_check)
    checked=_contract(contract)
    original=_input(checked,raw,halted,halt_check)
    right=_right_input(checked,right_raw,halted,halt_check)
    spec=_output_spec(checked,len(original.keys()|right.keys()) if right is not None else None)
    output=_table(artifact,spec,maximum=MAX_OUTPUT_BYTES,ordered=True,
                  halted=halted,halt_check=halt_check)
    if checked["format"]==RECONCILE_FORMAT:
        _verify_reconciliation(checked["specification"],original,right,output,halted,halt_check)
    elif checked["format"]==PROFILE_FORMAT:
        _verify_profile(checked["specification"],original,output,halted,halt_check)
    elif original!=output:
        raise DeliverableError("CSV_CONTENT_MISMATCH")
    # Compare canonical serialization as well: noncanonical output bytes fail.
    if artifact!=_serialize(spec,output,halted,halt_check):
        raise DeliverableError("CSV_CANONICAL_OUTPUT_REQUIRED")
    result=dict(format=RECONCILE_REPORT if right is not None else REPORT,contract_sha256=checked["contract_sha256"],
                plan_id=checked["plan_id"],input_sha256=sha256(raw).hexdigest(),
                artifact_sha256=sha256(artifact).hexdigest(),
                input_bytes=len(raw),artifact_bytes=len(artifact),rows=len(output),
                columns=list(spec["columns"]),key_column=spec["key_column"],
                checks=_checks(checked),
                local_criteria_passed=True,**dict.fromkeys(_FLAGS,False))
    if right is not None:
        result.update(right_input_sha256=sha256(right_raw).hexdigest(),right_input_bytes=len(right_raw))
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


def produce_csv(contract,raw,*,halted=None,halt_check=None,right_raw=None):
    """Produce actual UTF-8 CSV bytes, plus a separate deterministic QA report."""
    _permit(halted,halt_check)
    checked=_contract(contract)
    rows=_input(checked,raw,halted,halt_check)
    right=_right_input(checked,right_raw,halted,halt_check)
    if checked["format"]==RECONCILE_FORMAT:
        rows=_reconcile_rows(checked["specification"],rows,right,halted,halt_check)
    elif checked["format"]==PROFILE_FORMAT:
        rows=_profile_rows(checked["specification"],rows,halted,halt_check)
    artifact=_serialize(_output_spec(checked,len(rows)),rows,halted,halt_check)
    report=verify_csv(checked,raw,artifact,halted=halted,halt_check=halt_check,right_raw=right_raw)
    _permit(halted,halt_check)
    return dict(contract=checked,artifact=artifact,report=report)
