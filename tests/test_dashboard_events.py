import unittest
from nexus_exchange.dashboard_events import project

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
