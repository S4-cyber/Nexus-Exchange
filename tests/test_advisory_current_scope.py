import copy
import unittest
from datetime import datetime, timedelta, timezone

from nexus_exchange.advisory_current_scope import _compare_scope

NOW = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)


def pair():
    original = dict(evaluated_at=NOW.isoformat(), snapshot_sha256='a'*64,
                    schedule_sha256='b'*64, plan_id='c'*64,
                    scenario_sha256='d'*64, modeled_collection_wait_us=2000000,
                    source_hold=None, criteria=[{'criterion':'collection_timing','state':'LOCAL_CHECK_FITS'}],
                    reference_ids={'price':['e'*64]})
    current = copy.deepcopy(original)
    current.update(evaluated_at=(NOW+timedelta(seconds=1)).isoformat(),
                   snapshot_sha256='f'*64, schedule_sha256='1'*64,
                   modeled_collection_wait_us=1000000)
    return original,current


class CurrentScopeComparisonTests(unittest.TestCase):
    def compare(self, original, current, **opts):
        options=dict(created=NOW, now=NOW+timedelta(seconds=1))
        options.update(opts)
        return _compare_scope(original,current,**options)

    def test_clock_only_changes_preserve_absolute_collection_instant(self):
        old,new=pair()
        original=copy.deepcopy(old)
        fresh=copy.deepcopy(new)
        pin=self.compare(old,new)
        self.assertEqual(len(pin),64)
        self.assertEqual(pin,self.compare(old,old,now=NOW))
        self.assertEqual(old,original)
        self.assertEqual(new,fresh)

    def test_every_other_field_and_absolute_collection_drift_denied(self):
        old,new=pair()
        for change in (dict(plan_id='9'*64),dict(scenario_sha256='9'*64),
                       dict(source_hold='SOURCE_REVIEW_REQUIRED'),dict(criteria=[]),
                       dict(reference_ids={'price':[]}),dict(modeled_collection_wait_us=1000001),
                       dict(modeled_collection_wait_us=None)):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.compare(old,dict(new,**change))

    def test_old_future_and_expired_evaluations_rejected(self):
        old,new=pair()
        for changes in (dict(created=NOW+timedelta(seconds=2)),dict(now=NOW),
                        dict(now=NOW+timedelta(minutes=6))):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.compare(old,new,**changes)
        with self.assertRaises(ValueError):
            self.compare(old,dict(new,evaluated_at=(NOW-timedelta(seconds=1)).isoformat()))

    def test_schedule_and_snapshot_time_binding(self):
        old,new=pair()
        for change in (dict(schedule_sha256=old['schedule_sha256']),
                       dict(snapshot_sha256=old['snapshot_sha256'])):
            with self.assertRaises(ValueError):
                self.compare(old,dict(new,**change))
        with self.assertRaises(ValueError):
            self.compare(old,dict(old,schedule_sha256='9'*64),now=NOW)
        with self.assertRaises(ValueError):
            self.compare(old,dict(old,snapshot_sha256='9'*64),now=NOW)

    def test_unknown_collection_time_stays_unknown(self):
        old,new=pair()
        old['modeled_collection_wait_us']=None
        new['modeled_collection_wait_us']=None
        self.assertEqual(self.compare(old,new),self.compare(old,old,now=NOW))


class CurrentScopeLedgerTests(unittest.TestCase):
    from test_advisory_attempts import AdvisoryAttemptTests as fixtures
    setUp = fixtures.setUp
    reserve = fixtures.reserve

    def test_current_completion_failure_keeps_reservation_and_success_consumes_it(self):
        from unittest.mock import patch
        from nexus_exchange.advisory_attempts import AdvisoryAttemptStore
        from test_advisory_attempts import NOW, PLAN, fixture_review
        with AdvisoryAttemptStore(self.path) as store:
            r=self.reserve(store)
            current=dict(self.snapshot)
            opts=dict(now=NOW,approved=True,halted=False,worker_drained=True)
            with self.assertRaises(ValueError):
                store.complete_current(r['ticket'],r['request'],self.snapshot,None,b'owned fixture response',**opts)
            with patch('nexus_exchange.advisory_current_scope.review_current_response',side_effect=ValueError('drift')):
                with self.assertRaises(ValueError):
                    store.complete_current(r['ticket'],r['request'],self.snapshot,current,b'owned fixture response',**opts)
            self.assertEqual(store.status(PLAN,halted=False)['state'],'RESERVED')
            def reviewed(raw,request,original,fresh,**kwargs):
                if fresh!=current:
                    raise ValueError('wrong fixture')
                return dict(fixture_review(raw,request,original,**kwargs),current_scope_sha256='f'*64)
            with patch('nexus_exchange.advisory_current_scope.review_current_response',side_effect=reviewed):
                state=store.complete_current(r['ticket'],r['request'],self.snapshot,current,b'owned fixture response',**opts)
            self.assertEqual(state['state'],'REVIEWED')
            self.assertEqual(state['review']['current_scope_sha256'],'f'*64)
