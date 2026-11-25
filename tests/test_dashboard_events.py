import unittest
from nexus_exchange.dashboard_events import project, search_history

def event(state, task="a", target="fixture"):
    return dict(task_id=task,target=target,state=state,timestamp="2026-01-01T00:00:00Z")

class ProjectionTests(unittest.TestCase):
    def test_success(self):
        result=project([event("queued"),event("running"),event("succeeded")])
        self.assertEqual(result["successful_tasks"],1)
        self.assertEqual(result["tasks"],())
        self.assertEqual(len(result["history"]),3)
    def test_invalid_transition(self):
        with self.assertRaises(ValueError): project([event("succeeded")])
    def test_target_change(self):
        with self.assertRaises(ValueError): project([event("queued"),event("running",target="other")])
    def test_pagination(self):
        self.assertEqual(len(project([event("queued",str(i)) for i in range(11)],2)["tasks"]),1)

    def test_search_scans_older_events_before_applying_display_limit(self):
        events = [event("queued", task="older-id", target="Early Import")]
        events.extend(event("queued", task=str(i)) for i in range(101))
        events.append(event("cancelled", task="100"))
        history = project(events)["history"]
        for query in (" eArLY ", "OLDER-id"):
            with self.subTest(query=query):
                self.assertEqual(search_history(history, query), ([history[0]], 1))
        self.assertEqual(search_history(history, "cancelled"), ([history[-1]], 1))
        self.assertEqual(search_history(history, "absent"), ([], 0))
        for query in ("", "2026-01-01"):
            with self.subTest(query=query):
                self.assertEqual(search_history(history, query),
                                 (list(reversed(history[-100:])), len(history)))
