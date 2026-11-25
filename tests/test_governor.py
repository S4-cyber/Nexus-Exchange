import unittest
from nexus_exchange.governor import Action, decide


class GovernorTests(unittest.TestCase):
    def test_local_actions_only(self):
        allowed = {Action.RESEARCH_LOCAL, Action.EVALUATE, Action.DRAFT, Action.SIMULATE}
        for action in Action:
            with self.subTest(action=action):
                decision = decide(action, halted=False)
                self.assertEqual(decision.allowed, action in allowed)
                self.assertFalse(decision.external_authority)

    def test_halt_precedence(self):
        for action in Action:
            with self.subTest(action=action):
                self.assertEqual(decide(action, halted=True).reason, 'HALTED_OR_UNKNOWN')
                self.assertFalse(decide(action, halted=True).allowed)

    def test_unknown_halt_fails_closed(self):
        for value in (None, 0, 1, 'false', [], object()):
            self.assertFalse(decide(Action.DRAFT, halted=value).allowed)
        self.assertFalse(decide(Action.DRAFT).allowed)

    def test_untrusted_actions(self):
        for action in ('draft', 'payment', None, {}, 1, object()):
            self.assertFalse(decide(action, halted=False).allowed)
            self.assertEqual(decide(action, halted=False).reason, 'UNKNOWN_ACTION')

    def test_no_approval_bypass(self):
        with self.assertRaises(TypeError):
            decide(Action.PAYMENT, halted=False, approved=True)
        self.assertFalse(decide(Action.PAYMENT, halted=False).allowed)

    def test_restart_snapshot_does_not_enable_live_actions(self):
        self.assertFalse(decide(Action.DRAFT, halted=True).allowed)
        self.assertTrue(decide(Action.DRAFT, halted=False).allowed)
        self.assertFalse(decide(Action.OUTREACH, halted=False).allowed)
