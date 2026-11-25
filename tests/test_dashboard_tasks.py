import unittest
from nexus_exchange.dashboard_tasks import task_page

class DashboardTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(task_page([]).task_ids,())
    def test_overflow(self):
        ids=[str(i) for i in range(11)]
        self.assertEqual(task_page(ids).pages,2)
        self.assertEqual(task_page(ids,2).task_ids,("10",))
    def test_duplicate(self):
        with self.assertRaises(ValueError): task_page(["a","a"])
    def test_invalid_page(self):
        with self.assertRaises(ValueError): task_page([],2)
