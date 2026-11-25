import copy
import unittest
from datetime import timedelta
from unittest.mock import Mock

from nexus_exchange import sam_search
from nexus_exchange.checklist_store import context_for
from nexus_exchange.digital_deliverable import MAX_ROWS,MAX_COLUMNS,MAX_INPUT_BYTES,MAX_CELL_CHARS
from nexus_exchange.operator_capabilities import catalog,assess_lead,assess_requirements,CSV_ID
from nexus_exchange.review_ranking import RankingStore
from nexus_exchange.ranking_workspace import row_details
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_owner_profile import profile
from test_lead_store import NOW
import test_sam_search as sam


def requirements(**changes):
    value=dict(capability_id=CSV_ID,input_format="UTF8_CSV",input_bytes=200,max_cell_chars=30,
        preserve_all_fields=True,requires_deduplication=False,requires_inference=False,
        requires_formulas=False,specification=dict(input_sha256="a"*64,columns=["id","name"],
                                                    key_column="id",expected_rows=2))
    value.update(changes)
    return value


class OperatorCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.store=RankingStore(":memory:")
        self.addCleanup(self.store.__exit__,None,None,None)
        self.profile=profile()
        self.report=sam_search.search(sam.QUERY,sam.KEY,
            transport=Mock(return_value=(200,sam.page([
                sam.notice(1,title="Synthetic general IT services"),
                sam.notice(2,title="Synthetic CSV sorting"),
                sam.notice(3,title="Synthetic CSV normalization",active="No")]))),
            approved=True,halt_check=lambda:False,clock=lambda:NOW)
        self.store.record(self.report,now=NOW,halted=False)

    def rank(self,**changes):
        args=dict(profile=self.profile,now=NOW,halted=False)
        args.update(changes)
        return self.store.rank_review(**args)

    def by_title(self,**changes):
        return {r["title"]:r for r in self.rank(**changes)["rows"]}

    def test_catalog_is_bounded_and_uses_actual_limits(self):
        result=catalog(halted=False)
        entry=result["capabilities"][0]
        self.assertEqual(len(result["capabilities"]),1)
        self.assertEqual(entry["max_rows"],MAX_ROWS)
        self.assertEqual(entry["max_columns"],MAX_COLUMNS)
        self.assertEqual(entry["max_input_bytes"],MAX_INPUT_BYTES)
        self.assertEqual(entry["max_cell_chars"],MAX_CELL_CHARS)
        self.assertEqual(entry["capability_id"],CSV_ID)
        self.assertFalse(entry["external_authority"])
        self.assertFalse(entry["capability_verified_for_lead"])
        entry["max_rows"]=9999
        self.assertEqual(catalog(halted=False)["capabilities"][0]["max_rows"],MAX_ROWS)

    def test_only_narrow_title_hint_and_no_source_hold_override(self):
        rows=self.by_title()
        generic=rows["Synthetic general IT services"]["operator_capability"]
        match=rows["Synthetic CSV sorting"]["operator_capability"]
        held=rows["Synthetic CSV normalization"]["operator_capability"]
        self.assertEqual(generic["state"],"NO_IMPLEMENTED_TITLE_HINT")
        self.assertEqual(match["state"],"IMPLEMENTED_TITLE_HINT_ONLY")
        self.assertEqual(held["state"],"SOURCE_HELD")
        self.assertEqual(match["capability_ids"],[CSV_ID])
        self.assertFalse(match["requirements_verified"])
        self.assertFalse(match["zero_capital_verified"])
        self.assertFalse(match["delivery_feasibility_verified"])
        self.assertEqual(held["review_priority"],1)
        self.assertEqual(match["context"],rows["Synthetic CSV sorting"]["context"])

    def test_focus_only_within_existing_review_tiers(self):
        result=self.rank(operator_focus=True)
        self.assertTrue(result["operator_focus"])
        self.assertEqual(result["implemented_hint_count"],1)
        self.assertEqual(result["rows"][0]["title"],"Synthetic CSV sorting")
        self.assertEqual(result["rows"][-1]["review_tier"],"SOURCE_REVIEW_REQUIRED")
        self.assertEqual(self.rank()["implemented_hint_count"],1)
        # A positive general scenario outranks an unresolved CSV hint.
        lead=next(r for r in self.store.browse(now=NOW,profile=self.profile,halted=False)["leads"]
                  if r["title"]=="Synthetic general IT services")
        self.store.save(context_for(lead),scenario(),plan(),profile=self.profile,now=NOW,halted=False)
        self.assertEqual(self.rank(operator_focus=True)["rows"][0]["title"],lead["title"])

    def test_stale_and_unselected_sources_never_get_priority(self):
        for result in (self.rank(now=NOW+timedelta(days=2),operator_focus=True),
                       self.rank(profile=profile(sources=[]),operator_focus=True)):
            self.assertEqual(result["implemented_hint_count"],0)
            self.assertTrue(all(r["operator_capability"]["state"]=="SOURCE_HELD" for r in result["rows"]))

    def test_bounded_scan_counts_and_detail_disclosure(self):
        result=self.rank(limit=1,scan_limit=2,operator_focus=True)
        self.assertTrue(result["scan_truncated"])
        self.assertTrue(result["output_truncated"])
        self.assertLessEqual(result["implemented_hint_count"],result["evaluated"])
        self.assertIn("Operator capability:",row_details(result["rows"][0],result))
        self.assertIn("No verified delivery ability",row_details(result["rows"][0],result))

    def test_declared_structure_fits_not_verified(self):
        result=assess_requirements(requirements(),halted=False)
        self.assertTrue(result["declared_structure_fits"])
        self.assertFalse(result["source_bytes_checked"])
        self.assertFalse(result["requirements_verified"])
        self.assertFalse(result["execution_eligible"])
        self.assertFalse(result["zero_capital_verified"])

    def test_unknown_and_unsupported_requirements_hold(self):
        for changes,reason in (
                (dict(input_bytes=None),"DECLARED_SIZE_UNKNOWN"),
                (dict(input_bytes=MAX_INPUT_BYTES+1),"INPUT_SIZE_OUTSIDE_CAPABILITY"),
                (dict(max_cell_chars=MAX_CELL_CHARS+1),"CELL_SIZE_OUTSIDE_CAPABILITY"),
                (dict(input_format="OTHER"),"UNSUPPORTED_INPUT_FORMAT"),
                (dict(preserve_all_fields=False),"FIELD_TRANSFORMATION_UNSUPPORTED"),
                (dict(requires_deduplication=True),"DEDUPLICATION_UNSUPPORTED"),
                (dict(requires_inference=True),"INFERENCE_UNSUPPORTED"),
                (dict(requires_formulas=True),"FORMULAS_UNSUPPORTED"),
                (dict(specification=None),"DECLARED_SPECIFICATION_MISSING")):
            with self.subTest(reason=reason):
                result=assess_requirements(requirements(**changes),halted=False)
                self.assertFalse(result["declared_structure_fits"])
                self.assertIn(reason,result["reasons"])

    def test_schema_bounds_and_invalid_flags(self):
        spec=requirements()["specification"]
        for update in (dict(expected_rows=MAX_ROWS+1),dict(expected_rows=True),
                       dict(columns=["id"]*(MAX_COLUMNS+1)),dict(key_column="absent")):
            result=assess_requirements(requirements(specification=dict(spec,**update)),halted=False)
            self.assertIn("SPECIFICATION_OUTSIDE_CAPABILITY",result["reasons"])
        for changes in (dict(requires_formulas=1),dict(input_bytes=True),dict(capability_id="unknown"),
                        dict(external_authority=True),dict(input_format="anything")):
            with self.assertRaises(ValueError):
                assess_requirements(requirements(**changes),halted=False)

    def test_halt_and_invalid_focus_fail_closed(self):
        for state in (None,True,0):
            with self.assertRaises(PermissionError):
                catalog(halted=state)
            with self.assertRaises(PermissionError):
                assess_requirements(requirements(),halted=state)
        for focus in (None,1,"true"):
            with self.assertRaises(ValueError):
                self.rank(operator_focus=focus)
        self.assertFalse(self.store.db.in_transaction)

    def test_exact_historical_context_and_direct_hold(self):
        lead=next(r for r in self.store.browse(now=NOW,profile=self.profile,halted=False)["leads"]
                  if r["title"]=="Synthetic CSV sorting")
        for changed in (dict(lead,execution_eligible=True),dict(lead,external_authority=True)):
            with self.assertRaises(ValueError):
                assess_lead(changed,source_hold=None,halted=False)
        stale=dict(lead,blockers=list(lead["blockers"])+["OBSERVATION_STALE"])
        result=assess_lead(stale,source_hold=None,halted=False)
        self.assertEqual(result["state"],"SOURCE_HELD")
        self.assertEqual(result["review_priority"],1)


if __name__=="__main__":
    unittest.main()
