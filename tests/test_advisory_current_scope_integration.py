import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from nexus_exchange.advisory_attempts import AdvisoryAttemptStore
from nexus_exchange.advisory_current_scope import review_current_response
from nexus_exchange.local_advisory import build_request
from test_context_packet import snapshot, rehash, NOW
from test_local_advisory_integration import MODEL, wire


def refresh(original):
    fresh=copy.deepcopy(original)
    fresh["evaluated_at"]=(NOW+timedelta(microseconds=100)).isoformat(timespec="microseconds")
    fresh["schedule_sha256"]="9"*64
    fresh["modeled_collection_wait_us"]-=100
    return rehash(fresh)


class CurrentScopeIntegrationTests(unittest.TestCase):
    def test_exact_council_request_and_fresh_snapshot(self):
        original=snapshot(held=True,reference=True)
        fresh=refresh(original)
        request=build_request(original,MODEL,1,now=NOW,approved=True,halted=False)
        field=request["fields"][0]
        advice=[dict(field=field["field"],reason=field["state"],reference_id=field["reference_ids"][0])]
        result=review_current_response(wire(request,advice),request,original,fresh,
            now=NOW+timedelta(microseconds=100),approved=True,halted=False)
        self.assertEqual(result["current_snapshot_sha256"],fresh["snapshot_sha256"])
        self.assertEqual(result["advice"],advice)
        self.assertEqual(result["source_hold"],"SOURCE_REVIEW_REQUIRED")
        self.assertIs(result["external_authority"],False)
        self.assertIs(result["execution_eligible"],False)

    def test_valid_resealed_scope_drift_does_not_complete_attempt(self):
        original=snapshot()
        fresh=refresh(original)
        changed=refresh(snapshot(held=True))
        now=NOW+timedelta(microseconds=100)
        with tempfile.TemporaryDirectory() as root:
            with AdvisoryAttemptStore(Path(root)/"local-advisory.sqlite3") as store:
                reservation=store.reserve(original,MODEL,now=NOW,approved=True,halted=False)
                request=reservation["request"]
                raw=wire(request,[])
                with self.assertRaises(ValueError):
                    store.complete_current(reservation["ticket"],request,original,changed,raw,
                        now=now,approved=True,halted=False,worker_drained=True)
                self.assertEqual(store.status(original["plan_id"],halted=False)["state"],"RESERVED")
                result=store.complete_current(reservation["ticket"],request,original,fresh,raw,
                    now=now,approved=True,halted=False,worker_drained=True)
                self.assertEqual(result["state"],"REVIEWED")
                self.assertEqual(result["review"]["current_snapshot_sha256"],fresh["snapshot_sha256"])

    def test_resealed_wait_and_unknown_freshness_rejected(self):
        original=snapshot()
        fresh=refresh(original)
        fresh["modeled_collection_wait_us"]+=1
        rehash(fresh)
        request=build_request(original,MODEL,1,now=NOW,approved=True,halted=False)
        raw=wire(request,[])
        now=NOW+timedelta(microseconds=100)
        with self.assertRaises(ValueError):
            review_current_response(raw,request,original,fresh,now=now,approved=True,halted=False)
        with self.assertRaises(PermissionError):
            review_current_response(raw,request,original,refresh(original),now=now,approved=True,halted=None)
