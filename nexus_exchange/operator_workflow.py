"""Deterministic local work decomposition, not a commercial executor.

Only fixed implemented service templates; no arbitrary tools, instructions,
automatic confirmation, external delivery or durable source paths. The
historical projection reconstructs the workflow from the existing obligation
ledger, without claiming to re-read historical sources or prove publication.
"""
from .digital_deliverable import (
    FORMAT as CSV_FORMAT, JSON_FORMAT, PROFILE_FORMAT, RECONCILE_FORMAT,
    _contract, _checks, _permit, _FLAGS,
)
from .deliverable_obligations import artifact_reference, _qa
from .lead_store import _digest, _json

TEMPLATE_FORMAT="nexus-local-operator-workflow-template-v1"
PLAN_FORMAT="nexus-local-operator-workflow-plan-v1"
PROGRESS_FORMAT="nexus-local-operator-workflow-progress-v1"
FLAGS=tuple(dict.fromkeys((*_FLAGS,"commercial_delivery_completed",
                          "human_review_verified","publication_independently_verified")))
_SERVICES={
    CSV_FORMAT:("CSV standardization",1,
                "Validate exact CSV columns, unique key and declared row count.",
                "Sort by exact key and reorder columns; preserve every original field.",
                "Compare every output field to its keyed source row and canonical CSV bytes."),
    JSON_FORMAT:("JSON-to-CSV conversion",1,
                 "Validate a flat JSON array of exact string records, rejecting duplicate members.",
                 "Convert exact strings to quoted CSV in declared column order.",
                 "Reparse the original JSON and CSV; compare every field and canonical bytes."),
    PROFILE_FORMAT:("CSV quality report",1,
                    "Validate CSV schema, unique keys, row count and bounded safe cells.",
                    "Compute aggregate empty, whitespace, nonblank, distinct and length counts.",
                    "Separately recompute every column statistic and canonical CSV bytes."),
    RECONCILE_FORMAT:("Two-file CSV reconciliation",2,
                      "Validate both CSV schemas, independent row counts and unique keys.",
                      "Compare exact keys and fields; report union membership and change flags.",
                      "Recompute union membership, statuses, flags and canonical CSV bytes."),
}
_LOCAL_STEPS=("SCOPE","REQUIREMENTS","INPUT_PINS","VALIDATE","PRODUCE","QA")


def _seal(payload,field):
    return dict(payload,**{field:_digest(_json(payload))})


def _step(task_id,requires,mode,instruction):
    return dict(task_id=task_id,requires=list(requires),mode=mode,instruction=instruction)


def workflow_template(contract_format,*,halted=None):
    _permit(halted)
    if type(contract_format) is not str or contract_format not in _SERVICES:
        raise ValueError("unsupported workflow template")
    label,count,validate,produce,qa=_SERVICES[contract_format]
    tasks=[
        _step("SCOPE",(),"LOCAL_CHECK","Recheck the exact saved scenario, profile and source hold."),
        _step("REQUIREMENTS",("SCOPE",),"OWNER_INPUT","Declare input columns, unique key and exact row count(s)."),
        _step("INPUT_PINS",("REQUIREMENTS",),"LOCAL_CHECK",
              "Read and fingerprint both selected local files." if count==2 else "Read and fingerprint the selected local file."),
        _step("VALIDATE",("INPUT_PINS",),"LOCAL_CHECK",validate),
        _step("PRODUCE",("VALIDATE",),"LOCAL_PROCESS",produce),
        _step("QA",("PRODUCE",),"LOCAL_CHECK",qa),
        _step("REVIEW",("QA",),"OWNER_REVIEW","Inspect the exact local preview; determine whether it meets the requested work."),
        _step("EXPORT",("REVIEW",),"OPTIONAL_CONFIRMED_ACTION","If needed, confirm a new local CSV export; recheck the preview and never overwrite."),
        _step("REGISTER",("REVIEW",),"CONFIRMED_ACTION","Re-preview, then confirm registration of an existing exact-match artifact; export is not required."),
        _step("EXTERNAL_HOLD",("REGISTER",),"NOT_IMPLEMENTED","External delivery, acceptance and payment are not authorized or verified."),
    ]
    return _seal(dict(format=TEMPLATE_FORMAT,contract_format=contract_format,
        service_label=label,source_count=count,tasks=tasks,**dict.fromkeys(FLAGS,False)),
        "template_sha256")


def workflow_plan(contract,*,halted=None):
    _permit(halted)
    checked=_contract(contract)
    template=workflow_template(checked["format"],halted=halted)
    payload=dict(format=PLAN_FORMAT,template=template,
        plan_id=checked["plan_id"],contract_sha256=checked["contract_sha256"],
        specification=checked["specification"],required_qa_checks=_checks(checked),
        **dict.fromkeys(FLAGS,False))
    return _seal(payload,"workflow_sha256")


def _project(contract,report,reference,*,phase,halted,obligation_id=None):
    _permit(halted)
    plan=workflow_plan(contract,halted=halted)
    checked=_qa(_contract(contract),report)
    states={}
    for task in plan["template"]["tasks"]:
        key=task["task_id"]
        if key in _LOCAL_STEPS:
            state="HISTORICAL_LOCAL_QA_RECORDED" if phase=="HISTORICAL" else "LOCAL_PREVIEW_PASSED"
        elif key=="EXTERNAL_HOLD":
            state="NOT_AUTHORIZED"
        elif key=="REVIEW":
            state="OWNER_ACTION_RECORDED_NOT_REVIEW_PROOF" if phase in ("EXPORTED","HISTORICAL") else "REVIEW_REQUIRED"
        elif key=="EXPORT":
            state=("LOCAL_EXPORT_REPORTED" if phase=="EXPORTED" else
                   "PUBLICATION_NOT_ESTABLISHED" if phase=="HISTORICAL" else "OPTIONAL_CONFIRMATION_REQUIRED")
        else:
            state=("LOCAL_REGISTRATION_RECORDED" if phase=="HISTORICAL" else
                   "REPREVIEW_AND_CONFIRM_REQUIRED" if phase=="EXPORTED" else "CONFIRMATION_REQUIRED")
        states[key]=state
    payload=dict(format=PROGRESS_FORMAT,phase=phase,workflow=plan,
        qa_report_sha256=checked["report_sha256"],artifact_reference=reference,
        obligation_id=obligation_id,task_states=states,
        **dict.fromkeys(FLAGS,False))
    return _seal(payload,"progress_sha256")


def preview_progress(result,*,halted=None):
    """Project the producer's local QA metadata; not independent source proof."""
    _permit(halted)
    reference=artifact_reference(result)
    return _project(result["contract"],result["report"],reference,phase="PREVIEW",
                    halted=halted)


def export_progress(preview,exported,*,halted=None):
    """Only accept the exact preview and trusted local export response."""
    _permit(halted)
    current=preview_progress(preview,halted=halted)
    report=preview["report"]
    expected=dict(expected_contract=preview["contract"]["contract_sha256"],
                  expected_report=report["report_sha256"],
                  expected_artifact=report["artifact_sha256"],exported=True,
                  report=report,buyer_accepted=False,external_authority=False)
    if type(exported) is not dict or _json(exported)!=_json(expected):
        raise ValueError("workflow export response differs from reviewed preview")
    return _project(preview["contract"],report,current["artifact_reference"],
                    phase="EXPORTED",halted=halted)


def historical_progress(record,plan_id,*,halted=None):
    _permit(halted)
    from .obligation_workspace import validate_record
    checked=validate_record(record,plan_id)
    binding=checked["binding"]
    return _project(binding["contract"],binding["qa_report"],binding["artifact_reference"],
                    phase="HISTORICAL",obligation_id=checked["obligation_id"],halted=halted)


def template_text(contract_format,*,halted=None):
    template=workflow_template(contract_format,halted=halted)
    return "\n".join(["WORKFLOW — "+template["service_label"]+" (planned, not executed)",
        *(str(index)+". "+task["instruction"] for index,task in enumerate(template["tasks"],1)),
        "No commercial authority. Select files and enter requirements before preview."])


def progress_text(progress):
    # Presentation of projections generated only by the functions above.
    labels={"LOCAL_PREVIEW_PASSED":"Local preview passed",
            "HISTORICAL_LOCAL_QA_RECORDED":"Historical local QA recorded",
            "OWNER_ACTION_RECORDED_NOT_REVIEW_PROOF":"Owner action recorded; review not proven",
            "REVIEW_REQUIRED":"Review required",
            "OPTIONAL_CONFIRMATION_REQUIRED":"Optional confirmation required",
            "PUBLICATION_NOT_ESTABLISHED":"Publication not established",
            "LOCAL_EXPORT_REPORTED":"Local export reported",
            "CONFIRMATION_REQUIRED":"Confirmation required",
            "REPREVIEW_AND_CONFIRM_REQUIRED":"Re-preview and confirm",
            "LOCAL_REGISTRATION_RECORDED":"Local registration recorded",
            "NOT_AUTHORIZED":"Not authorized"}
    plan=progress["workflow"]
    lines=["WORKFLOW — "+plan["template"]["service_label"],
           "Workflow SHA-256: "+plan["workflow_sha256"],
           "Progress is local evidence only; not independent verification or commercial completion."]
    for index,task in enumerate(plan["template"]["tasks"],1):
        key=task["task_id"]
        lines.append(str(index)+". ["+labels[progress["task_states"][key]]+"] "+task["instruction"])
    return "\n".join(lines)
