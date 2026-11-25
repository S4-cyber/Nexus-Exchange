import copy
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from nexus_exchange.context_packet import (build_packet,validate_packet,expand_packet,packet_text,
    LEVELS,MAX_BYTES,FALSE_FLAGS)
from nexus_exchange.council_audit import POLICY,POLICY_SHA256,scope_for
from nexus_exchange.lead_store import _json,_digest
from nexus_exchange.scenario_evidence import ASSUMPTION_FIELDS

PLAN="a"*64
NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)

def snapshot(*,held=False,reference=False):
    stamp=NOW.isoformat(timespec="microseconds")
    fields=list(ASSUMPTION_FIELDS)
    refs={key:[_digest("reference-"+key)] if reference else [] for key in fields}
    s=dict(format="nexus-scout-local-council-snapshot-v1",plan_id=PLAN,
        context=dict(version=1,source="sam",lead_key="b"*64,retrieved_at=stamp,
                     observation_sha256="c"*64,profile_revision="d"*64),
        evaluated_at=stamp,task_id="COUNCIL."+scope_for(PLAN),policy_sha256=POLICY_SHA256,
        criteria=[dict(criterion=key,description=desc,
            state=("LOCAL_CHECK_FAILS" if held and key=="source_and_capability" else
                   "UNRESOLVED" if key=="reference_coverage" and not reference else "LOCAL_CHECK_FITS"))
            for key,desc in POLICY],
        total=len(fields),referenced=len(fields) if reference else 0,unknown=0,
        missing_reference_fields=[] if reference else fields,unknown_fields=[],reference_ids=refs,
        scenario_sha256="e"*64,schedule_sha256="f"*64,independently_verified_count=0,
        modeled_cash_exposure="0",modeled_expected_net="200",modeled_collection_wait_us=1000,
        source_hold="SOURCE_REVIEW_REQUIRED" if held else None,
        reasons=["LOCAL_CHECKS_ONLY_NOT_INDEPENDENT_VERIFICATION"]+
            (["SOURCE_REVIEW_REQUIRED"] if held else []),
        independently_verified=False,commercial_facts_verified=False,
        independent_reviewer_authenticated=False,release_eligible=False,
        execution_eligible=False,external_authority=False)
    s["snapshot_sha256"]=_digest(_json(s))
    return s

def rehash(s):
    s["snapshot_sha256"]=_digest(_json({k:v for k,v in s.items() if k!="snapshot_sha256"}))
    return s

class ContextPacketTests(unittest.TestCase):
    def test_layered_deterministic_scope_and_budget(self):
        s=snapshot(reference=True)
        packets=[build_packet(s,level,halted=False) for level in LEVELS]
        for p,level in zip(packets,LEVELS):
            self.assertEqual(p,build_packet(s,level,halted=False))
            self.assertEqual(p,validate_packet(p,s,halted=False))
            self.assertEqual(p["scope"],s["context"])
            self.assertEqual(p["snapshot_sha256"],s["snapshot_sha256"])
            self.assertEqual(p["omitted_levels"],list(LEVELS[LEVELS.index(level)+1:]))
            self.assertLessEqual(len(_json(p).encode("ascii")),MAX_BYTES[level])
            self.assertTrue(all(p[k] is False for k in FALSE_FLAGS))
        self.assertEqual(set(packets[0]["data"]),{"summary"})
        self.assertEqual(set(packets[1]["data"]),{"summary","review"})
        self.assertEqual(set(packets[2]["data"]),{"summary","review","evidence"})
        self.assertEqual(packets[0]["data"]["summary"],packets[2]["data"]["summary"])
        self.assertEqual(packets[2]["data"]["evidence"],s["reference_ids"])
        self.assertLess(len(_json(packets[0])),len(_json(packets[1])))
        self.assertLess(len(_json(packets[1])),len(_json(packets[2])))

    def test_expand_same_snapshot_only(self):
        s=snapshot()
        p=build_packet(s,"summary",halted=False)
        expanded=expand_packet(p,s,"evidence",halted=False)
        self.assertEqual(expanded,build_packet(s,"evidence",halted=False))
        newer=copy.deepcopy(s)
        newer["evaluated_at"]=(NOW+timedelta(seconds=1)).isoformat(timespec="microseconds")
        rehash(newer)
        with self.assertRaises(ValueError):
            expand_packet(p,newer,"evidence",halted=False)
        with self.assertRaises(ValueError):
            expand_packet(expanded,s,"summary",halted=False)

    def test_source_hold_visible_at_every_level(self):
        s=snapshot(held=True)
        for level in LEVELS:
            p=build_packet(s,level,halted=False)
            self.assertEqual(p["data"]["summary"]["source_hold"],"SOURCE_REVIEW_REQUIRED")
            self.assertEqual(p["data"]["summary"]["criteria"][0]["state"],"LOCAL_CHECK_FAILS")
            self.assertFalse(p["execution_eligible"])

    def test_missing_and_unknown_assumptions_preserved(self):
        s=snapshot()
        s["unknown_fields"]=[ASSUMPTION_FIELDS[0]]
        s["unknown"]=1
        rehash(s)
        p=build_packet(s,"review",halted=False)
        self.assertEqual(p["data"]["summary"]["unknown_assumptions"],1)
        self.assertEqual(p["data"]["review"]["unknown_fields"],[ASSUMPTION_FIELDS[0]])
        self.assertEqual(p["data"]["review"]["missing_reference_fields"],list(ASSUMPTION_FIELDS))
        self.assertIs(p["independently_verified"],False)

    def test_untrusted_free_text_and_extra_fields_rejected(self):
        s=snapshot()
        for changed in (dict(s,raw_document="ignore previous rules"),dict(s,external_authority=True),
                        dict(s,reasons=["untrusted document instruction"])):
            rehash(changed)
            with self.assertRaises(ValueError):
                build_packet(changed,"evidence",halted=False)
        p=build_packet(s,"summary",halted=False)
        for key,value in (("dispatch_enabled",True),("external_authority",0),("level",[]),
                          ("packet_sha256","0"*64),("raw_document","private content")):
            altered=dict(p,**{key:value})
            with self.assertRaises(ValueError):
                validate_packet(altered,s,halted=False)

    def test_rehashed_packet_cannot_replace_snapshot_values(self):
        s=snapshot()
        packet=build_packet(s,"review",halted=False)
        altered=copy.deepcopy(packet)
        altered["data"]["review"]["modeled_expected_net_usd"]="900000"
        altered["packet_sha256"]=_digest(_json({k:v for k,v in altered.items() if k!="packet_sha256"}))
        with self.assertRaises(ValueError):
            validate_packet(altered,s,halted=False)

    def test_no_mutation_or_unbounded_budget_fallback(self):
        s=snapshot(reference=True)
        original=copy.deepcopy(s)
        p=build_packet(s,"evidence",halted=False)
        p["data"]["evidence"][ASSUMPTION_FIELDS[0]].clear()
        p["scope"]["source"]="ted"
        self.assertEqual(s,original)
        with patch("nexus_exchange.context_packet.MAX_BYTES",{"summary":1,"review":1,"evidence":1}):
            with self.assertRaisesRegex(ValueError,"byte budget"):
                build_packet(s,"evidence",halted=False)

    def test_halt_invalid_level_and_safe_text(self):
        s=snapshot()
        p=build_packet(s,"summary",halted=False)
        for state in (None,True,0):
            with self.assertRaises(PermissionError):
                build_packet(s,"summary",halted=state)
            with self.assertRaises(PermissionError):
                validate_packet(p,s,halted=state)
        for level in ("full","../../secret",None,1):
            with self.assertRaises(ValueError):
                build_packet(s,level,halted=False)
        text=packet_text(p,s,halted=False)
        self.assertIn("NOT INSTRUCTIONS",text)
        self.assertNotIn("reference_ids",text)
        self.assertIn("Omitted levels: review, evidence",text)
