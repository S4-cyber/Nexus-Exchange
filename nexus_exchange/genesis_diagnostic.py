"""Owned, offline Genesis lifecycle diagnostic.

Only fixed synthetic fixtures in a fresh temporary directory. No user data,
external transport, customer, contract, real invoice, or real payment.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from . import sam_search
from .cash_feasibility import COSTS
from .checklist_store import context_for
from .csv_workspace import CsvWorkspace
from .finance_workspace import FinanceWorkspace
from .lead_store import _digest, _json
from .obligation_workspace import ObligationWorkspace
from .operator_capabilities import CSV_ID, assess_requirements
from .owner_profile import ProfileStore
from .review_ranking import RankingStore
from .runtime_guard import RuntimeGuard
from .scenario_evidence import ScenarioEvidenceStore, ASSUMPTION_FIELDS

FORMAT="nexus-owned-genesis-diagnostic-v1"
_START=datetime(2026,11,24,12,tzinfo=timezone.utc)
_RAW=b"name,id,category\nBeta,002,Research\nAlpha,001,Design\n"
_EXPECTED=b'"id","name","category"\r\n"001","Alpha","Design"\r\n"002","Beta","Research"\r\n'
_TITLE="Owned synthetic CSV sorting work sample"
_FLAGS=("actual_opportunity_verified","requirements_verified","buyer_accepted",
        "contract_awarded","invoice_issued","payment_received","revenue_realized",
        "funds_available","zero_capital_verified","independently_verified",
        "execution_eligible","external_authority","reinvestment_authorized",
        "commercial_dispatch_enabled","release_eligible")


def _check(condition,code):
    if not condition:
        raise RuntimeError("GENESIS_DIAGNOSTIC_"+code)


def _denied(operation,exception):
    try:
        operation()
    except exception:
        return
    raise RuntimeError("GENESIS_DIAGNOSTIC_NEGATIVE_CONTROL_FAILED")


def _false(record,keys):
    _check(all(record.get(k) is False for k in keys),"AUTHORITY")


def run_diagnostic(*,confirmed=None):
    """Run the fixed local lifecycle, then delete all synthetic working files.

    Confirmation is exclusively for this owned temporary simulation.
    No path, external URL, callback, credential, amount or user profile input.
    """
    if confirmed is not True:
        raise PermissionError("explicit owned Genesis diagnostic confirmation required")
    # A controlled fixture clock models the timeline and avoids using the
    # host date as a commercial fact. It advances, including across restart.
    now=[_START]
    clock=lambda:now[0]
    issue=(_START+timedelta(days=18)).date()
    due=issue+timedelta(days=30)
    first_day=issue+timedelta(days=10)
    final_day=due+timedelta(days=5)
    counts={"fixture_transport_calls":0,"external_requests":0}
    checks=[]
    def pass_check(name,condition=True):
        _check(condition,name)
        checks.append(name)
    def transport(params,key):
        counts["fixture_transport_calls"]+=1
        _check(counts["fixture_transport_calls"]==1 and params["offset"]==0
               and params["title"]=="csv sorting" and key=="owned-fixture-only","TRANSPORT_SCOPE")
        base=dict(type="Combined Synopsis/Solicitation",active="Yes",postedDate="2026-11-20",
                  responseDeadLine=(_START+timedelta(days=7)).isoformat(),naicsCode="541519")
        rows=[dict(base,noticeId="1"*32,title="Owned synthetic general IT services"),
              dict(base,noticeId="2"*32,title=_TITLE),
              dict(base,noticeId="3"*32,title="Owned synthetic CSV normalization",active="No")]
        return 200,_json(dict(totalRecords=len(rows),limit=sam_search.PAGE_SIZE,
                              offset=0,opportunitiesData=rows)).encode("ascii")

    profile=dict(mode="genesis",budget="0.00",hours_per_week=20,sources=["sam"],
                 naics=["541519"],cpv=[],keywords=["csv sorting"])
    scenario=dict(currency="USD",compensation="200.00",probability_delivery_bps=8000,
        probability_payment_given_delivery_bps=7500,delivery_days=7,
        payment_days_after_delivery=30,labor_hours=10,costs=dict.fromkeys(COSTS,"0.00"))
    timing=dict(preparation_days=2,preparation_hours=4,
        delivery_start=(_START+timedelta(days=11)).isoformat(),
        delivery_deadline=(_START+timedelta(days=18)).isoformat())
    spec=dict(input_sha256=sha256(_RAW).hexdigest(),columns=["id","name","category"],
              key_column="id",expected_rows=2)

    with TemporaryDirectory(prefix="nexus-genesis-owned-") as scratch:
        directory=Path(scratch).resolve()
        source=directory/"owned-input.csv"
        output=directory/"owned-output.csv"
        source.write_bytes(_RAW)
        evidence=directory/"owned-assumption-reference.txt"
        evidence.write_bytes(b"Owned synthetic assumption reference; not factual evidence.")
        acceptance=directory/"owned-acceptance-claim.txt"
        acceptance.write_bytes(b"Owned synthetic acceptance claim; no customer or real award.")
        with RuntimeGuard(directory,clock=clock) as guard:
            pass_check("STARTUP_HALTED",guard.is_set())
            guard.resume()
            report=sam_search.search(sam_search.Query(_START.date()-timedelta(days=7),
                _START.date(),"csv sorting"),"owned-fixture-only",
                approved=True,halt_check=guard.is_set,transport=transport,clock=clock)
            pass_check("FIXTURE_DISCOVERY",report["returned"]==3 and report["requests"]==1
                       and not report["truncated"])
            _check(all(row["execution_eligible"] is False and row["external_authority"] is False
                       for row in report["leads"]),"DISCOVERY_AUTHORITY")
            with ProfileStore(directory/"owner-profile.sqlite3") as store:
                store.save(profile,halted=guard.is_set())
            with RankingStore(directory/"scout-leads.sqlite3") as store:
                pass_check("ARCHIVE_IDEMPOTENT",store.record(report,now=clock(),halted=guard.is_set())==3
                    and store.record(report,now=clock(),halted=guard.is_set())==0)
                ranking=store.rank_review(profile=profile,now=clock(),operator_focus=True,
                                          halted=guard.is_set())
                first=ranking["rows"][0]
                pass_check("CAPABILITY_FOCUS",first["title"]==_TITLE
                    and first["operator_capability"]["state"]=="IMPLEMENTED_TITLE_HINT_ONLY"
                    and ranking["implemented_hint_count"]==1
                    and ranking["rows"][-1]["review_tier"]=="SOURCE_REVIEW_REQUIRED")
                leads=store.browse(now=clock(),profile=profile,halted=guard.is_set())["leads"]
                lead=next(row for row in leads if row["title"]==_TITLE)
                ctx=context_for(lead)
                plan_id=store.save(ctx,scenario,timing,profile=profile,now=clock(),halted=guard.is_set())
                model=store.evaluate(plan_id,profile=profile,now=clock(),halted=guard.is_set())
                pass_check("ZERO_EXPOSURE_MODEL",model["cash"]["modeled_cash_exposure"]==Decimal("0")
                    and model["cash"]["modeled_expected_net"]==Decimal("120")
                    and model["cash"]["modeled_budget_fit"] is True
                    and model["schedule"]["modeled_schedule_fit"] is True
                    and model["genesis_verified"] is False)
            declared=assess_requirements(dict(capability_id=CSV_ID,input_format="UTF8_CSV",
                input_bytes=len(_RAW),max_cell_chars=8,preserve_all_fields=True,
                requires_deduplication=False,requires_inference=False,requires_formulas=False,
                specification=spec),halted=guard.is_set())
            pass_check("DECLARED_STRUCTURE_ONLY",declared["declared_structure_fits"] is True
                and declared["requirements_verified"] is False and declared["source_bytes_checked"] is False)
            guard.council_action("register",plan_id)
            missing=guard.council_action("run_once",plan_id)
            pass_check("COUNCIL_MISSING_EVIDENCE",missing["review"]["status"]=="NEEDS_EVIDENCE"
                and missing["ledger"]["attempts_used"]==1)
            now[0]+=(timedelta(seconds=1))
            with ScenarioEvidenceStore(directory/"scout-leads.sqlite3") as store:
                for field in ASSUMPTION_FIELDS:
                    store.attach(plan_id,field,evidence,profile=profile,now=clock(),
                                 halted=guard.is_set(),halt_check=guard.is_set)
            reviewed=guard.council_action("run_once",plan_id)
            pass_check("COUNCIL_REVIEW_ONLY",reviewed["review"]["status"]=="ADVANCE_REVIEW_ONLY"
                and reviewed["ledger"]["attempts_used"]==2
                and reviewed["snapshot"]["referenced"]==len(ASSUMPTION_FIELDS)
                and reviewed["snapshot"]["independently_verified_count"]==0)
            _false(reviewed,("commercial_facts_verified","execution_eligible","external_authority","release_eligible"))
            _denied(lambda:guard.council_action("run_once",plan_id),PermissionError)
            pass_check("COUNCIL_TERMINAL_NO_REPLAY")

            csv=CsvWorkspace(plan_id,action=guard.csv_file_action,blocked_check=guard.is_set)
            preview=csv.preview(source,"id,name,category","id","2")
            pass_check("ARTIFACT_EXACT_QA",preview["artifact"]==_EXPECTED
                and preview["report"]["local_criteria_passed"] is True
                and preview["report"]["input_sha256"]==spec["input_sha256"])
            now[0]+=timedelta(seconds=1)
            csv.export(output,confirmed=True)
            pass_check("ACTUAL_LOCAL_ARTIFACT",output.read_bytes()==_EXPECTED)
            csv.preview(source,"id,name,category","id","2")
            _denied(lambda:csv.export(output,confirmed=True),ValueError)
            pass_check("NO_OVERWRITE",output.read_bytes()==_EXPECTED)
            csv.preview(source,"id,name,category","id","2")
            obligation=csv.register(output,confirmed=True)
            pass_check("OBLIGATION_BOUND",obligation["binding"]["qa_report"]==preview["report"]
                and obligation["buyer_accepted"] is False)
            # Advance the fixture clock to the modeled delivery date. No
            # attempt is made to re-open the stale procurement opportunity.
            now[0]=_START+timedelta(days=18)
            ledger=ObligationWorkspace(plan_id,action=guard.csv_obligation_action,blocked_check=guard.is_set)
            ledger.inspect(obligation["obligation_id"])
            obligation=ledger.note("acceptance_claim_noted",acceptance,confirmed=True)
            pass_check("UNVERIFIED_ACCEPTANCE_NOTE",len(obligation["notes"])==1
                and obligation["buyer_accepted"] is False and obligation["invoice_eligible"] is False)
            finance=FinanceWorkspace(obligation,action=guard.simulated_invoice_action,blocked_check=guard.is_set)
            invoice=finance.preview(issue.isoformat())
            pass_check("INVOICE_TERMS_PINNED",invoice["gross_cents"]==20000 and invoice["due_date"]==due.isoformat()
                and invoice["obligation_head_sha256"]==obligation["head_sha256"])
            finance.create(confirmed=True)
            now[0]+=timedelta(days=10)
            partial=finance.payment("SIM-OWNEDFIRST","75.13",first_day.isoformat(),confirmed=True)
            pass_check("PARTIAL_RECONCILIATION",partial["simulated_received_cents"]==7513
                and partial["simulated_outstanding_cents"]==12487 and partial["payment_received"] is False)
            _denied(lambda:finance.payment("SIM-OWNEDFIRST","1",first_day.isoformat(),confirmed=True),ValueError)
            finance.refresh()
            _denied(lambda:finance.payment("SIM-OWNEDOVER","124.88",first_day.isoformat(),confirmed=True),ValueError)
            pass_check("DUPLICATE_AND_OVERPAYMENT_DENIED",finance.refresh()==partial)
            held=finance.cashflow(first_day.isoformat(),"2500")
            pass_check("PARTIAL_ALLOCATION_HELD",held["allocation_modeled"] is False)
            guard.set()
            _denied(lambda:guard.simulated_invoice_action("find",plan_id),PermissionError)
            pass_check("EMERGENCY_HALT_DENIES")

        now[0]+=timedelta(seconds=1)
        with RuntimeGuard(directory,clock=clock) as reopened:
            pass_check("RESTART_REQUIRES_RESUME",reopened.is_set())
            _denied(lambda:reopened.simulated_invoice_action("find",plan_id),PermissionError)
            reopened.resume()
            history=reopened.council_action("history",plan_id)
            pass_check("DURABLE_COUNCIL_AUDIT",history["attempts_used"]==2
                and all(row["audit_state"]=="RECORDED" for row in history["attempts"]))
            recovered=reopened.csv_obligation_action("history",plan_id,obligation_id=obligation["obligation_id"])
            finance=FinanceWorkspace(recovered,action=reopened.simulated_invoice_action,blocked_check=reopened.is_set)
            pass_check("DURABLE_OBLIGATION_AND_RECEIPTS",recovered==obligation and finance.refresh()==partial)
            now[0]=_START+timedelta(days=53)
            final=finance.payment("SIM-OWNEDFINAL","124.87",final_day.isoformat(),confirmed=True)
            pass_check("EXACT_SETTLEMENT",final["state"]=="SIMULATED_SETTLED"
                and final["simulated_received_cents"]==20000 and final["simulated_outstanding_cents"]==0)
            late=finance.projection((due+timedelta(days=1)).isoformat())
            pass_check("FUTURE_RECEIPT_EXCLUDED",late["simulated_overdue_cents"]==12487
                and late["future_dated_receipts_cents"]==12487 and late["days_overdue"]==1)
            allocation=finance.cashflow(final_day.isoformat(),"2500")
            pass_check("PROTECTED_RESERVE_MODEL",allocation["modeled_total_cost_cents"]==0
                and allocation["modeled_net_as_of_cents"]==20000 and allocation["allocation_modeled"] is True
                and allocation["modeled_protected_reserve_cents"]==5000
                and allocation["modeled_reinvestment_cents"]==15000)
            _false(allocation,("payment_received","revenue_realized","funds_available",
                               "reinvestment_authorized","external_authority","zero_capital_verified"))
            pass_check("FINAL_LEDGER_STABLE",finance.refresh()==final and output.read_bytes()==_EXPECTED)
            payload=dict(format=FORMAT,mode="OWNED_OFFLINE_FIXTURE_ONLY",checks=checks,
                fixture_transport_calls=counts["fixture_transport_calls"],external_requests=counts["external_requests"],
                source_page_sha256=report["page_sha256"][0],plan_id=plan_id,
                capability_catalog_sha256=ranking["capability_catalog_sha256"],
                council_attempts=history["attempts_used"],
                council_report_sha256=reviewed["report_sha256"],
                assumption_references=reviewed["snapshot"]["referenced"],
                independently_verified_assumptions=0,artifact_sha256=preview["report"]["artifact_sha256"],
                qa_report_sha256=preview["report"]["report_sha256"],
                obligation_id=obligation["obligation_id"],obligation_head_sha256=obligation["head_sha256"],
                invoice_id=invoice["invoice_id"],receipt_head_sha256=final["head_sha256"],
                allocation_sha256=allocation["projection_sha256"],
                modeled_pre_payment_exposure_cents=0,modeled_probability_adjusted_net_cents=12000,
                hypothetical_gross_cents=20000,hypothetical_received_cents=final["simulated_received_cents"],
                hypothetical_outstanding_cents=final["simulated_outstanding_cents"],
                hypothetical_protected_reserve_cents=allocation["modeled_protected_reserve_cents"],
                hypothetical_reinvestment_cents=allocation["modeled_reinvestment_cents"],
                **dict.fromkeys(_FLAGS,False))
    # Return only after the isolated temporary directory was cleaned up.
    return dict(payload,report_sha256=_digest(_json(payload)))


if __name__=="__main__":
    print(_json(run_diagnostic(confirmed=True)))
