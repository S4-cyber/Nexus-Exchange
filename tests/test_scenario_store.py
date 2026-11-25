import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from nexus_exchange.checklist_store import context_for
from nexus_exchange.scenario_store import ScenarioStore
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_lead_store import NOW, reports
from test_owner_profile import profile


class ScenarioStoreTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)/"scout.sqlite3"
        self.profile=profile(mode="genesis",budget="0",hours_per_week=20)
        self.report=reports()[0]
        with ScenarioStore(self.path) as store:
            store.record(self.report,now=NOW,halted=False)
            self.lead=store.browse(now=NOW,source="sam",profile=self.profile,
                                   halted=False)["leads"][0]
        self.context=context_for(self.lead)

    def save(self,store,raw=None,timing=None,**kw):
        args=dict(profile=self.profile,now=NOW,halted=False)
        args.update(kw)
        return store.save(self.context,scenario() if raw is None else raw,
                          plan() if timing is None else timing,**args)

    def test_restart_and_fresh_models(self):
        with ScenarioStore(self.path) as store:
            key=self.save(store)
        with ScenarioStore(self.path) as store:
            saved=store.get(key,halted=False)
            self.assertEqual(saved["context"],self.context)
            self.assertEqual(saved["scenario"]["compensation"],"200.00")
            self.assertEqual(saved["plan"]["delivery_start"],"2026-12-05T12:00:00.000000+00:00")
            self.assertNotIn("modeled_expected_net",saved)
            result=store.evaluate(key,profile=self.profile,now=NOW,halted=False)
            self.assertEqual(str(result["cash"]["modeled_expected_net"]),"120.00")
            self.assertTrue(result["schedule"]["modeled_schedule_fit"])
            self.assertFalse(result["execution_eligible"])
            self.assertFalse(result["independently_verified"])
            self.assertFalse(result["external_authority"])

    def test_replay_canonical_and_immutable(self):
        with ScenarioStore(self.path) as store:
            a=self.save(store)
            b=self.save(store,scenario(compensation="200"),
                plan(delivery_start="2026-12-05T04:00:00-08:00"),now=NOW+timedelta(hours=1))
            self.assertEqual(a,b)
            self.assertEqual(store.get(a,halted=False)["created_at"],NOW.isoformat(timespec="microseconds"))
            c=self.save(store,scenario(compensation="201"))
            self.assertNotEqual(a,c)
            self.assertEqual({x["plan_id"] for x in store.list(self.context,halted=False)},{a,c})

    def test_reassess_at_new_clock(self):
        with ScenarioStore(self.path) as store:
            key=self.save(store)
            early=store.evaluate(key,profile=self.profile,now=NOW,halted=False)
            late=store.evaluate(key,profile=self.profile,now=NOW+timedelta(days=7),halted=False)
            self.assertTrue(early["schedule"]["modeled_submission_fit"])
            self.assertFalse(late["schedule"]["modeled_submission_fit"])
            self.assertIn("OBSERVATION_STALE",late["schedule"]["reasons"])
            self.assertNotEqual(early["schedule"]["schedule_sha256"],late["schedule"]["schedule_sha256"])

    def test_observation_supersession_blocks_reassessment(self):
        with ScenarioStore(self.path) as store:
            key=self.save(store)
            updated=copy.deepcopy(self.report)
            later=NOW+timedelta(minutes=1)
            updated["leads"][0]["retrieved_at"]=later.isoformat()
            updated["leads"][0]["title"]="Revised synthetic scope"
            store.record(updated,now=later,halted=False)
            with self.assertRaisesRegex(ValueError,"observation or profile changed"):
                store.evaluate(key,profile=self.profile,now=later,halted=False)
            with self.assertRaisesRegex(ValueError,"observation or profile changed"):
                self.save(store,now=later)
            self.assertEqual(store.get(key,halted=False)["context"],self.context)

    def test_profile_change_and_missing_archive(self):
        with ScenarioStore(self.path) as store:
            key=self.save(store)
            changed=profile(mode="genesis",budget="0",hours_per_week=25)
            with self.assertRaisesRegex(ValueError,"observation or profile changed"):
                store.evaluate(key,profile=changed,now=NOW,halted=False)
            store.db.execute("DELETE FROM scout_observations_v1")
            with self.assertRaisesRegex(ValueError,"archived observation unavailable"):
                store.evaluate(key,profile=self.profile,now=NOW,halted=False)

    def test_forged_context_and_invalid_schema(self):
        with ScenarioStore(self.path) as store:
            forged=dict(self.context,observation_sha256="a"*64)
            with self.assertRaises(ValueError):
                store.save(forged,scenario(),plan(),profile=self.profile,now=NOW,halted=False)
            for raw,timing in ((scenario(compensation=True),plan()),
                               (scenario(),plan(delivery_start="tomorrow")),
                               (scenario(),dict(plan(),approval=True))):
                with self.assertRaises(ValueError):
                    self.save(store,raw,timing)
            self.assertEqual(store.list(self.context,halted=False),[])

    def test_halt_and_unknown_clock(self):
        with ScenarioStore(self.path) as store:
            key=self.save(store)
            for halted in (True,None,0):
                with self.assertRaises(PermissionError):
                    self.save(store,halted=halted)
                with self.assertRaises(PermissionError):
                    store.get(key,halted=halted)
                with self.assertRaises(PermissionError):
                    store.list(self.context,halted=halted)
                with self.assertRaises(PermissionError):
                    store.evaluate(key,profile=self.profile,now=NOW,halted=halted)
            with self.assertRaises(ValueError):
                store.evaluate(key,profile=self.profile,now=NOW-timedelta(seconds=1),halted=False)

    def test_tamper_and_identity_checks(self):
        with ScenarioStore(self.path) as store:
            key=self.save(store)
            store.db.execute("UPDATE scout_scenarios_v1 SET payload='{}' WHERE plan_id=?",(key,))
            with self.assertRaises(ValueError):
                store.get(key,halted=False)
            with self.assertRaises(ValueError):
                store.list(self.context,halted=False)
            with self.assertRaises(ValueError):
                self.save(store)

    def test_capacity_replay_and_transaction_rollback(self):
        with ScenarioStore(self.path) as store:
            key=self.save(store)
            with patch("nexus_exchange.scenario_store.MAX_PLANS",1):
                self.assertEqual(self.save(store),key)
                with self.assertRaisesRegex(ValueError,"capacity"):
                    self.save(store,scenario(compensation="201"))
            self.assertFalse(store.db.in_transaction)
            self.assertEqual(len(store.list(self.context,halted=False)),1)
            self.assertNotEqual(self.save(store,scenario(compensation="202")),key)

    def test_bounded_list_and_invalid_key(self):
        with ScenarioStore(self.path) as store:
            for i in range(3):
                self.save(store,scenario(compensation=str(200+i)))
            self.assertEqual(len(store.list(self.context,limit=2,halted=False)),2)
            for limit in (0,101,True):
                with self.assertRaises(ValueError):
                    store.list(self.context,limit=limit,halted=False)
            with self.assertRaises(ValueError):
                store.get("not-a-key",halted=False)
            self.assertIsNone(store.get("a"*64,halted=False))

    def test_unknown_costs_remain_unknown(self):
        costs=scenario()["costs"]
        costs["software"]=None
        with ScenarioStore(self.path) as store:
            key=self.save(store,scenario(costs=costs),plan(delivery_deadline=None))
            result=store.evaluate(key,profile=self.profile,now=NOW,halted=False)
            self.assertIsNone(result["cash"]["modeled_cash_exposure"])
            self.assertIsNone(result["schedule"]["modeled_schedule_fit"])
            self.assertFalse(result["external_authority"])

    def test_archive_store_compatibility(self):
        from nexus_exchange.lead_store import LeadStore
        with ScenarioStore(self.path) as store:
            key=self.save(store)
        with LeadStore(self.path) as store:
            rows=store.browse(now=NOW,source="sam",halted=False)
            self.assertEqual(rows["returned"],1)
        with ScenarioStore(self.path) as store:
            self.assertIsNotNone(store.get(key,halted=False))
