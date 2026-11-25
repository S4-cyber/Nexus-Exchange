"""Conservative catalogue of Operator's implemented local work capabilities.

Title hints help review order only. They are not extracted requirements,
customer demand, capacity, pricing, platform permission, or eligibility.
"""
import re
from .checklist_store import context_for
from .governor import Action, decide
from .lead_store import _digest, _json
from .owner_profile import BLOCKED_REASONS, PROFILE_SOURCES, reported_codes

FORMAT="nexus-operator-capabilities-v1"
CSV_ID="csv_preserve_and_standardize_v2"
JSON_ID="json_string_records_to_csv_v1"
PROFILE_ID="csv_column_quality_profile_v1"
_PROFILE_HINTS=(("CSV_QUALITY_REPORT",r"\bcsv\s+(?:column\s+)?quality\s+report\b"),
                ("CSV_COMPLETENESS_REPORT",r"\bcsv\s+(?:column\s+)?completeness\s+report\b"),
                ("CSV_DATA_PROFILING",r"\bcsv\s+data\s+profiling\b"))
_JSON_HINTS=(("JSON_TO_CSV",r"\bjson(?:\s*-\s*|\s+)to(?:\s*-\s*|\s+)csv\b"),)
_HINTS=(
    ("CSV_SORT",r"\bcsv\s+(?:row\s+)?sort(?:ing)?\b"),
    ("CSV_STANDARDIZE",r"\bcsv\s+(?:data\s+)?standard(?:iz|is)(?:ation|e|ing)\b"),
    ("CSV_NORMALIZE",r"\bcsv\s+(?:data\s+)?normali[sz](?:ation|e|ing)\b"),
    ("CSV_REORDER",r"\bcsv\s+(?:column\s+)?reorder(?:ing)?\b"),
)
_FLAGS=("requirements_verified","capability_verified_for_lead","delivery_feasibility_verified",
        "commercial_facts_verified","zero_capital_verified","independently_verified",
        "execution_eligible","external_authority","dispatch_enabled")
_TASKS=(
    "Obtain original authorized input and exact buyer requirements; title alone is insufficient.",
    "Check UTF-8 CSV, size, columns, key, expected row count and exact field preservation.",
    "Confirm no cleansing, deduplication, inferred values, formula execution or other unsupported work.",
    "Independently verify actual payment terms, costs, data-use permission and delivery capability.",
    "Select a saved scenario and perform local sample QA; obtain separate approval for any external action.",
)


_JSON_TASKS=(
    "Obtain authorized UTF-8 JSON: one array of flat records, exact fields, all values strings.",
    "Confirm unique key, exact expected row count and column order; no type coercion or nested data.",
    "Verify permission, actual payment terms, costs and delivery requirements independently.",
    "Review the local CSV sample; obtain separate approval for any external action.",
)


_PROFILE_TASKS=(
    "Obtain authorized UTF-8 CSV with exact declared columns, unique key and row count.",
    "Confirm aggregate empty, whitespace-only, nonblank, distinct nonblank and length statistics are the required output.",
    "No row-level values, inferred corrections, factual accuracy certification or external delivery.",
    "Verify permissions, actual payment terms, costs and delivery requirements separately.",
)


def _permit(halted):
    decision=decide(Action.RESEARCH_LOCAL,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)


def catalog(*,halted=None):
    """Construct fresh data from implemented backend constants, not marketing labels."""
    _permit(halted)
    from .digital_deliverable import (
        FORMAT as CONTRACT_FORMAT, JSON_FORMAT, PROFILE_FORMAT, PROFILE_COLUMNS, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES,
        MAX_ROWS, MAX_COLUMNS, MAX_CELL_CHARS,
    )
    entry=dict(capability_id=CSV_ID,label="CSV preservation and standardization",
        stage="IMPLEMENTED_LOCAL_WORK_SAMPLE",contract_format=CONTRACT_FORMAT,
        input_format="UTF8_CSV",output_format="UTF8_CSV",max_input_bytes=MAX_INPUT_BYTES,
        max_output_bytes=MAX_OUTPUT_BYTES,max_rows=MAX_ROWS,max_columns=MAX_COLUMNS,
        max_cell_chars=MAX_CELL_CHARS,operations=["REORDER_COLUMNS","SORT_UNIQUE_KEYS",
            "CANONICAL_CSV_SERIALIZATION","EXACT_FIELD_COMPARISON"],
        excluded=["DEDUPLICATION","DATA_CLEANSING","MISSING_VALUE_INFERENCE",
            "FORMULA_EXECUTION","NON_CSV_INPUT","EXTERNAL_DELIVERY"],
        title_hint_codes=[k for k,_ in _HINTS],review_tasks=list(_TASKS),
        local_processing_only=True,**dict.fromkeys(_FLAGS,False))
    json_entry=dict(entry,capability_id=JSON_ID,label="Flat JSON string records to CSV",
        contract_format=JSON_FORMAT,input_format="UTF8_JSON_RECORDS",
        operations=["EXACT_JSON_RECORD_SCHEMA","REORDER_COLUMNS","SORT_UNIQUE_KEYS",
                    "CANONICAL_CSV_SERIALIZATION","EXACT_FIELD_COMPARISON"],
        excluded=["NESTED_JSON","NON_STRING_VALUES","DUPLICATE_JSON_MEMBERS","DEDUPLICATION",
                  "DATA_CLEANSING","MISSING_VALUE_INFERENCE","FORMULA_EXECUTION","EXTERNAL_DELIVERY"],
        title_hint_codes=[k for k,_ in _JSON_HINTS],review_tasks=list(_JSON_TASKS))
    profile_entry=dict(entry,capability_id=PROFILE_ID,label="CSV column completeness and distinctness report",
        contract_format=PROFILE_FORMAT,output_columns=list(PROFILE_COLUMNS),
        operations=["EXACT_COLUMN_COUNTS","EXACT_DISTINCT_NONBLANK_COUNTS","EXACT_LENGTH_RANGE",
                    "CANONICAL_CSV_SERIALIZATION"],
        excluded=["ROW_LEVEL_OUTPUT","FACTUAL_ACCURACY_CERTIFICATION","DATA_CLEANSING","DEDUPLICATION",
                  "MISSING_VALUE_INFERENCE","FORMULA_EXECUTION","NON_CSV_INPUT","EXTERNAL_DELIVERY"],
        title_hint_codes=[k for k,_ in _PROFILE_HINTS],review_tasks=list(_PROFILE_TASKS))
    payload=dict(format=FORMAT,capabilities=[entry,json_entry,profile_entry],**dict.fromkeys(_FLAGS,False))
    return dict(payload,catalog_sha256=_digest(_json(payload)))


def assess_lead(lead,*,source_hold,halted=None):
    """Attach an advisory, scope-bound title signal without changing source holds."""
    _permit(halted)
    ctx=context_for(lead)
    source=lead["source"]
    title=lead.get("title")
    if (type(title) is not str or not 1<=len(title)<=512 or source not in PROFILE_SOURCES
            or type(lead.get("blockers")) is not list
            or type(lead.get("research_candidate_at_collection")) is not bool
            or type(lead.get("collection_truncated")) is not bool
            or source_hold not in (None,"SOURCE_REVIEW_REQUIRED","CONTRACTOR_INTELLIGENCE_ONLY",
                                   "SOURCE_NOT_SELECTED")):
        raise ValueError("invalid historical capability input")
    # The source hold is derived by the existing trusted ranking policy.
    # Independently retain known adverse observations even if the caller
    # accidentally omits its hold.
    held=(source_hold is not None or source=="usaspending"
          or not lead["research_candidate_at_collection"] or lead["collection_truncated"]
          or bool(BLOCKED_REASONS.intersection(lead["blockers"])))
    # Do not infer exact work from sector codes, broad data/IT terms,
    # query strings or owner keywords. Only literal bounded title hints.
    csv_matches=[key for key,pattern in _HINTS if re.search(pattern,title,re.IGNORECASE|re.ASCII)]
    json_matches=[key for key,pattern in _JSON_HINTS if re.search(pattern,title,re.IGNORECASE|re.ASCII)]
    profile_matches=[key for key,pattern in _PROFILE_HINTS if re.search(pattern,title,re.IGNORECASE|re.ASCII)]
    matches=csv_matches+json_matches+profile_matches
    ids=([CSV_ID] if csv_matches else [])+([JSON_ID] if json_matches else [])+([PROFILE_ID] if profile_matches else [])
    tasks=(list(_TASKS) if csv_matches else [])+(list(_JSON_TASKS) if json_matches else [])+(list(_PROFILE_TASKS) if profile_matches else [])
    codes=reported_codes(source,lead)
    status=("SOURCE_HELD" if held else
            "IMPLEMENTED_TITLE_HINT_ONLY" if matches else "NO_IMPLEMENTED_TITLE_HINT")
    payload=dict(format="nexus-operator-lead-fit-v1",context=ctx,
        catalog_sha256=catalog(halted=False)["catalog_sha256"],
        state=status,source_hold=source_hold,reported_codes=codes,
        capability_ids=ids,title_hint_codes=matches,
        review_priority=0 if status=="IMPLEMENTED_TITLE_HINT_ONLY" else 1,
        review_tasks=tasks if matches else [
            "Inspect original requirements; no implemented capability can be inferred from this title."],
        title_only=True,**dict.fromkeys(_FLAGS,False))
    return dict(payload,assessment_sha256=_digest(_json(payload)))


def assess_requirements(raw,*,halted=None):
    """Assess an explicit owner-declared spec, not an automatically inferred one.

    Only structural compatibility is assessed. Actual source cells, byte hash,
    output constraints and live scope must still pass the existing producer.
    """
    _permit(halted)
    from .digital_deliverable import (
        MAX_INPUT_BYTES, MAX_ROWS, MAX_COLUMNS, MAX_CELL_CHARS, _spec,
    )
    fields={"capability_id","input_format","input_bytes","max_cell_chars",
            "preserve_all_fields","requires_deduplication","requires_inference",
            "requires_formulas","specification"}
    if type(raw) is not dict or set(raw)!=fields:
        raise ValueError("complete declared capability requirements required")
    if type(raw["capability_id"]) is not str or raw["capability_id"] not in (CSV_ID,JSON_ID,PROFILE_ID):
        raise ValueError("unknown implemented capability")
    if type(raw["input_format"]) is not str or raw["input_format"] not in ("UTF8_CSV","UTF8_JSON_RECORDS","OTHER"):
        raise ValueError("unknown declared input format")
    for key in ("preserve_all_fields","requires_deduplication","requires_inference","requires_formulas"):
        if type(raw[key]) is not bool:
            raise ValueError("explicit declared requirement flags required")
    for key in ("input_bytes","max_cell_chars"):
        v=raw[key]
        if v is not None and (type(v) is not int or not 0<=v<=10**9):
            raise ValueError("bounded declared size or unknown required")
    spec=raw["specification"]
    reasons=[]
    if raw["input_format"]!=("UTF8_JSON_RECORDS" if raw["capability_id"]==JSON_ID else "UTF8_CSV"):
        reasons.append("UNSUPPORTED_INPUT_FORMAT")
    if raw["input_bytes"] is None or raw["max_cell_chars"] is None:
        reasons.append("DECLARED_SIZE_UNKNOWN")
    if raw["input_bytes"] is not None and not 1<=raw["input_bytes"]<=MAX_INPUT_BYTES:
        reasons.append("INPUT_SIZE_OUTSIDE_CAPABILITY")
    if raw["max_cell_chars"] is not None and raw["max_cell_chars"]>MAX_CELL_CHARS:
        reasons.append("CELL_SIZE_OUTSIDE_CAPABILITY")
    if raw["capability_id"]==PROFILE_ID:
        if raw["preserve_all_fields"]:
            reasons.append("ROW_LEVEL_OUTPUT_UNSUPPORTED_FOR_PROFILE")
    elif not raw["preserve_all_fields"]:
        reasons.append("FIELD_TRANSFORMATION_UNSUPPORTED")
    for key,reason in (("requires_deduplication","DEDUPLICATION_UNSUPPORTED"),
                       ("requires_inference","INFERENCE_UNSUPPORTED"),
                       ("requires_formulas","FORMULAS_UNSUPPORTED")):
        if raw[key]:
            reasons.append(reason)
    # _spec enforces actual implementation column, row and key bounds;
    # retain a reason for an unsupported declared schema instead of coercion.
    normalized=None
    if spec is None:
        reasons.append("DECLARED_SPECIFICATION_MISSING")
    else:
        try:
            normalized=_spec(spec)
        except ValueError:
            reasons.append("SPECIFICATION_OUTSIDE_CAPABILITY")
    payload=dict(format="nexus-declared-operator-requirements-v1",
        capability_id=raw["capability_id"],catalog_sha256=catalog(halted=False)["catalog_sha256"],
        declared_input=dict(input_format=raw["input_format"],input_bytes=raw["input_bytes"],
            max_cell_chars=raw["max_cell_chars"],preserve_all_fields=raw["preserve_all_fields"],
            requires_deduplication=raw["requires_deduplication"],requires_inference=raw["requires_inference"],
            requires_formulas=raw["requires_formulas"],specification=normalized),
        declared_structure_fits=not reasons,reasons=reasons,
        source_bytes_checked=False,**dict.fromkeys(_FLAGS,False))
    return dict(payload,assessment_sha256=_digest(_json(payload)))


def detail_text(assessment):
    labels={"SOURCE_HELD":"Source held — capability cannot override it",
            "IMPLEMENTED_TITLE_HINT_ONLY":"Implemented local service title hint — requirements not verified",
            "NO_IMPLEMENTED_TITLE_HINT":"No implemented title hint — inspect manually"}
    return "\n".join(["Operator capability: "+labels[assessment["state"]],
        "Signals: "+(", ".join(assessment["title_hint_codes"]) or "None"),
        "Catalogue fingerprint: "+assessment["catalog_sha256"],
        "Capability review tasks:",*("  [ ] "+t for t in assessment["review_tasks"]),
        "No verified delivery ability, zero-capital qualification or execution authority."])
