import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nexus_exchange.advisory_attempts import AdvisoryAttemptStore
from nexus_exchange.local_advisory import _digest

NOW = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
PLAN = "a" * 64
MODEL = "b" * 64
SNAP = "c" * 64


def fixture_request(snapshot, model, attempt, *, now, approved, halted):
    payload = dict(model_sha256=model, snapshot_sha256=snapshot["snapshot_sha256"],
                   attempt=attempt, created_at=now.isoformat(timespec="microseconds"))
    return dict(payload, request_sha256=_digest(payload))


def fixture_review(raw, request, snapshot, *, now, approved, halted):
    if raw != b"owned fixture response" or request["snapshot_sha256"] != snapshot["snapshot_sha256"]:
        raise ValueError("fixture rejection")
    return dict(request_sha256=request["request_sha256"], response_sha256="d" * 64,
                independently_verified=False, external_authority=False)


class AdvisoryAttemptTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "local-advisory.sqlite3"
        self.snapshot = dict(plan_id=PLAN, snapshot_sha256=SNAP)
        for name, fn in (("build_request", fixture_request), ("review_response", fixture_review)):
            p = patch("nexus_exchange.advisory_attempts." + name, side_effect=fn)
            p.start()
            self.addCleanup(p.stop)

    def reserve(self, store, **kwargs):
        args = dict(now=NOW, approved=True, halted=False)
        args.update(kwargs)
        return store.reserve(self.snapshot, MODEL, **args)

    def fail(self, store, ticket, **kwargs):
        args = dict(now=NOW, approved=True, halted=False, worker_drained=True)
        args.update(kwargs)
        return store.fail(ticket, "WORKER_FAILED", **args)

    def test_restart_and_model_change_cannot_reset_three_attempts(self):
        for n in range(1, 4):
            with AdvisoryAttemptStore(self.path) as store:
                reservation = self.reserve(store, now=NOW + timedelta(seconds=n))
                self.assertEqual(reservation["ticket"]["attempt"], n)
                with self.assertRaises(PermissionError):
                    self.reserve(store, now=NOW + timedelta(seconds=n))
                state = self.fail(store, reservation["ticket"], now=NOW + timedelta(seconds=n))
                self.assertEqual(state["attempts_used"], n)
            self.snapshot["snapshot_sha256"] = _digest({"revision": n})
        with AdvisoryAttemptStore(self.path) as store:
            self.assertEqual(state["state"], "ESCALATED")
            with self.assertRaises(PermissionError):
                store.reserve(self.snapshot, "e" * 64, now=NOW + timedelta(seconds=4), approved=True, halted=False)

    def test_exact_completion_and_no_replay(self):
        with AdvisoryAttemptStore(self.path) as store:
            r = self.reserve(store)
            with self.assertRaises(ValueError):
                store.complete(r["ticket"], dict(r["request"], attempt=2), self.snapshot,
                               b"owned fixture response", now=NOW, approved=True, halted=False, worker_drained=True)
            self.assertEqual(store.status(PLAN, halted=False)["state"], "RESERVED")
            with self.assertRaises(ValueError):
                store.complete(r["ticket"], r["request"], self.snapshot, b"invalid",
                               now=NOW, approved=True, halted=False, worker_drained=True)
            result = store.complete(r["ticket"], r["request"], self.snapshot, b"owned fixture response",
                                    now=NOW, approved=True, halted=False, worker_drained=True)
            self.assertEqual(result["state"], "REVIEWED")
            self.assertFalse(result["external_authority"])
            with self.assertRaises(PermissionError):
                self.reserve(store)
            with self.assertRaises(ValueError):
                self.fail(store, r["ticket"])

    def test_recovery_requires_halt_and_worker_drain_and_consumes_attempt(self):
        with AdvisoryAttemptStore(self.path) as store:
            r = self.reserve(store)
        with AdvisoryAttemptStore(self.path) as store:
            for changes in (dict(halted=False), dict(exclusive_owner=1), dict(worker_drained=False)):
                args = dict(now=NOW, halted=True, exclusive_owner=True, worker_drained=True)
                args.update(changes)
                with self.assertRaises(PermissionError):
                    store.recover_interrupted(PLAN, **args)
            state = store.recover_interrupted(PLAN, now=NOW, halted=True, exclusive_owner=True, worker_drained=True)
            self.assertEqual(state["state"], "INTERRUPTED")
            self.assertEqual(state["attempts_used"], 1)
            self.assertEqual(self.reserve(store)["ticket"]["attempt"], 2)
            with self.assertRaises(ValueError):
                self.fail(store, r["ticket"])

    def test_halt_unknown_consent_drain_and_backward_clock_denied(self):
        with AdvisoryAttemptStore(self.path) as store:
            for opts in (dict(halted=True), dict(halted=None), dict(halted=0), dict(approved=1)):
                with self.assertRaises(PermissionError):
                    self.reserve(store, **opts)
            r = self.reserve(store)
            with self.assertRaises(PermissionError):
                self.fail(store, r["ticket"], worker_drained=False)
            with self.assertRaises(ValueError):
                self.fail(store, r["ticket"], now=NOW-timedelta(seconds=1))
            self.assertEqual(store.status(PLAN, halted=False)["state"], "RESERVED")

    def test_integrity_and_rollback(self):
        with AdvisoryAttemptStore(self.path) as store:
            r = self.reserve(store)
            store.db.execute("CREATE TRIGGER fail_update BEFORE UPDATE ON advisory_attempts_v1 BEGIN SELECT RAISE(ABORT,'fixture'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                self.fail(store, r["ticket"])
            self.assertFalse(store.db.in_transaction)
            self.assertEqual(store.status(PLAN, halted=False)["state"], "RESERVED")
            store.db.execute("DROP TRIGGER fail_update")
            self.fail(store, r["ticket"])
            store.db.execute("UPDATE advisory_attempts_v1 SET payload='{}'")
            with self.assertRaises(ValueError):
                store.status(PLAN, halted=False)

    def test_two_connections_cannot_reserve_same_attempt(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        with AdvisoryAttemptStore(self.path):
            pass
        barrier = Barrier(2)
        def run():
            with AdvisoryAttemptStore(self.path) as store:
                barrier.wait(timeout=10)
                try:
                    return self.reserve(store)
                except PermissionError:
                    return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(run)
            b = pool.submit(run)
            self.assertEqual(sum(x.result(timeout=15) is not None for x in (a, b)), 1)

    def test_existing_only_and_capacity(self):
        with self.assertRaises(ValueError):
            AdvisoryAttemptStore(self.path, existing_only=True)
        self.assertFalse(self.path.exists())
        with AdvisoryAttemptStore(self.path) as store:
            self.reserve(store)
            self.snapshot["plan_id"] = "f" * 64
            with patch("nexus_exchange.advisory_attempts.MAX_TASKS", 1):
                with self.assertRaises(ValueError):
                    self.reserve(store)
        with AdvisoryAttemptStore(self.path, existing_only=True) as store:
            self.assertEqual(store.status(PLAN, halted=False)["attempts_used"], 1)


    def test_ledger_read_bounds_storage_before_text_decode(self):
        with AdvisoryAttemptStore(self.path) as store:
            self.reserve(store)
            original = store.db.execute("SELECT payload,digest FROM advisory_attempts_v1").fetchone()
            seen = []
            def decode(raw):
                seen.append(len(raw))
                return raw.decode("utf-8")
            store.db.text_factory = decode
            self.assertEqual(store.status(PLAN, halted=False)["state"], "RESERVED")
            self.assertEqual(seen, [])
            for column, value in (
                ("payload", "x" * 8193), ("payload", "x\x00" + "x" * 8192),
                ("payload", "é" * 4097), ("payload", b"{}"),
                ("digest", "a" * 65), ("digest", b"a" * 64),
                ("digest", b"\xff" * 64),
            ):
                with self.subTest(column=column, kind=type(value).__name__, size=len(value)):
                    store.db.execute("UPDATE advisory_attempts_v1 SET payload=?,digest=?", original)
                    if value == b"\xff" * 64:
                        store.db.execute("UPDATE advisory_attempts_v1 SET digest=CAST(? AS TEXT)", (value,))
                    else:
                        store.db.execute("UPDATE advisory_attempts_v1 SET " + column + "=?", (value,))
                    seen.clear()
                    with self.assertRaises(ValueError):
                        store.preview_budget(PLAN, halted=False)
                    self.assertEqual(seen, [])
                    self.assertFalse(store.db.in_transaction)
                    self.assertEqual(store.db.execute("SELECT COUNT(*) FROM advisory_attempts_v1").fetchone(), (1,))
            store.db.execute("UPDATE advisory_attempts_v1 SET payload=?,digest=?", original)
            self.assertEqual(store.status(PLAN, halted=False)["state"], "RESERVED")

    def test_runtime_enumeration_bounds_corrupt_keys_and_rolls_back(self):
        with AdvisoryAttemptStore(self.path) as store:
            self.reserve(store)
            original = store.db.execute("SELECT payload,digest FROM advisory_attempts_v1").fetchone()
            seen = []
            def decode(raw):
                seen.append(len(raw))
                return raw.decode("utf-8")
            store.db.text_factory = decode
            self.assertEqual(store._runtime_pending(now=NOW), 1)
            for value in ("x" * 8193, "a" * 64 + "\x00" + "x" * 8192, b"a" * 64, b"\xff" * 64):
                with self.subTest(kind=type(value).__name__, size=len(value)):
                    store.db.execute("DELETE FROM advisory_attempts_v1 WHERE plan_id!=?", (PLAN,))
                    if value == b"\xff" * 64:
                        store.db.execute("INSERT INTO advisory_attempts_v1 VALUES (CAST(? AS TEXT),?,?)",
                                         (value, *original))
                    else:
                        store.db.execute("INSERT INTO advisory_attempts_v1 VALUES (?,?,?)", (value, *original))
                    seen.clear()
                    with self.assertRaises(ValueError):
                        store._runtime_recover_all(now=NOW)
                    self.assertEqual(seen, [])
                    self.assertFalse(store.db.in_transaction)
                    self.assertEqual(store.db.execute("SELECT COUNT(*) FROM advisory_attempts_v1").fetchone(), (2,))
                    self.assertEqual(store.status(PLAN, halted=False)["state"], "RESERVED")


if __name__ == "__main__":
    unittest.main()
