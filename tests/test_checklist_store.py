import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock,patch
from nexus_exchange.checklist_store import ChecklistStore,context_for
from nexus_exchange.lead_store import LeadStore
from nexus_exchange import usaspending_search
from test_lead_store import reports,NOW,OPTS
from test_owner_profile import profile
import test_usaspending_search as spending

class ChecklistTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/"todo.sqlite3"
        self.leads=LeadStore(":memory:")
        self.addCleanup(self.leads.__exit__,None,None,None)
        self.report=reports()[0]
        self.leads.record(self.report,now=NOW,halted=False)

    def row(self,**kw):
        args=dict(now=NOW,source="sam",profile=profile(),halted=False)
        args.update(kw)
        return self.leads.browse(**args)["leads"][0]

    def context(self,**kw):
        return context_for(self.row(**kw))

    def save(self,store,context=None,**kw):
        args=dict(task_key="source",state="evidence_noted",reference="Official notice section 2",
            now=NOW,expected_revision=None,halted=False)
        args.update(kw)
        return store.save(self.context() if context is None else context,**args)

    def test_roundtrip_and_no_authority(self):
        context=self.context()
        with ChecklistStore(self.path) as store:
            initial=store.load(context,halted=False)
            self.assertEqual(initial["total"],9)
            self.assertIsNone(initial["revision"])
            result=self.save(store)
            self.assertEqual(result["evidence_noted"],1)
        with ChecklistStore(self.path) as store:
            saved=store.load(context,halted=False)
            self.assertEqual(saved,result)
            self.assertFalse(saved["independent_verification_complete"])
            self.assertFalse(saved["external_authority"])
            self.assertFalse(saved["execution_eligible"])
            self.assertTrue(all(not task["independently_verified"] for task in saved["tasks"]))

    def test_profile_change_is_separate_context(self):
        with ChecklistStore(self.path) as store:
            self.save(store)
            changed=self.context(profile=profile(hours_per_week=21))
            self.assertEqual(store.load(changed,halted=False)["evidence_noted"],0)
            self.assertEqual(store.load(self.context(profile=None),halted=False)["total"],7)
            self.assertEqual(store.load(self.context(),halted=False)["evidence_noted"],1)

    def test_new_observation_is_separate_context(self):
        old=self.context()
        newer=copy.deepcopy(self.report)
        later=NOW+timedelta(minutes=1)
        newer["leads"][0]["retrieved_at"]=later.isoformat()
        with ChecklistStore(self.path) as store:
            self.save(store)
            self.leads.record(newer,now=later,halted=False)
            current=self.context(now=later)
            self.assertNotEqual(old["observation_sha256"],current["observation_sha256"])
            self.assertEqual(store.load(current,halted=False)["evidence_noted"],0)
            self.assertEqual(store.load(old,halted=False)["evidence_noted"],1)

    def test_exact_lookup_and_scope(self):
        row=self.row()
        result=self.leads.browse(now=NOW,source="sam",lead_key=row["key"],profile=profile(),halted=False)
        self.assertEqual(result["leads"],[row])
        self.assertEqual(self.leads.browse(now=NOW,source="sam",lead_key="a"*64,halted=False)["returned"],0)
        for options in (dict(lead_key="bad",source="sam"),dict(lead_key=row["key"])):
            with self.assertRaises(ValueError):
                self.leads.browse(now=NOW,halted=False,**options)

    def test_concurrent_edit_rejected(self):
        context=self.context()
        with ChecklistStore(self.path) as first,ChecklistStore(self.path) as second:
            old=second.load(context,halted=False)
            saved=self.save(first)
            with self.assertRaisesRegex(ValueError,"reload"):
                self.save(second,task_key="cost",expected_revision=old["revision"])
            current=self.save(second,task_key="cost",expected_revision=saved["revision"])
            self.assertEqual(current["evidence_noted"],2)

    def test_reset_and_followup(self):
        with ChecklistStore(self.path) as store:
            saved=self.save(store)
            follow=self.save(store,state="needs_followup",reference="Check current status",
                expected_revision=saved["revision"])
            self.assertEqual(follow["evidence_noted"],0)
            reset=self.save(store,state="pending",reference="",expected_revision=follow["revision"])
            self.assertEqual(reset["tasks"][0]["state"],"pending")
            self.assertEqual(reset["tasks"][0]["reference"],"")
            self.assertNotEqual(reset["revision"],saved["revision"])

    def test_invalid_states_references_and_clock(self):
        with ChecklistStore(self.path) as store:
            for options in (dict(state="approved"),dict(task_key="send_bid"),
                    dict(reference=""),dict(reference="x"*241),dict(reference="a\nb"),
                    dict(state="pending"),dict(now=NOW-timedelta(seconds=1)),
                    dict(now=NOW.replace(tzinfo=None))):
                with self.subTest(options=options),self.assertRaises(ValueError):
                    self.save(store,**options)
            self.assertIsNone(store.load(self.context(),halted=False)["revision"])

    def test_halt_and_capacity(self):
        with ChecklistStore(self.path) as store:
            for halted in (None,True,0):
                with self.assertRaises(PermissionError):
                    self.save(store,halted=halted)
                with self.assertRaises(PermissionError):
                    store.load(self.context(),halted=halted)
            with patch("nexus_exchange.checklist_store.MAX_CONTEXTS",0):
                with self.assertRaises(ValueError):
                    self.save(store)
            self.assertIsNone(store.load(self.context(),halted=False)["revision"])

    def test_tamper_and_forged_context(self):
        with ChecklistStore(self.path) as store:
            self.save(store)
            store.db.execute("UPDATE scout_checklists_v1 SET payload='{}'")
            with self.assertRaises(ValueError):
                store.load(self.context(),halted=False)
        for key,value in (("observation_sha256","bad"),("external_authority",True),("todo",[])):
            row=self.row()
            row[key]=value
            with self.assertRaises(ValueError):
                context_for(row)

    def test_all_evidence_noted_is_not_permission(self):
        with ChecklistStore(self.path) as store:
            result=store.load(self.context(),halted=False)
            for task in result["tasks"]:
                result=self.save(store,task_key=task["key"],expected_revision=result["revision"])
            self.assertEqual(result["evidence_noted"],result["total"])
            self.assertFalse(result["independent_verification_complete"])
            self.assertFalse(result["external_authority"])
            self.assertFalse(result["execution_eligible"])

    def test_contractor_specific_tasks(self):
        report=usaspending_search.search(spending.QUERY,
            transport=Mock(return_value=(200,spending.page([spending.award()]))),**OPTS)
        self.leads.record(report,now=NOW,halted=False)
        context=self.context(source="usaspending")
        with ChecklistStore(self.path) as store:
            result=store.load(context,halted=False)
            self.assertEqual(result["tasks"][1]["key"],"demand")
            with self.assertRaises(ValueError):
                self.save(store,context=context,task_key="source")
            saved=self.save(store,context=context,task_key="demand")
            self.assertEqual(saved["evidence_noted"],1)
