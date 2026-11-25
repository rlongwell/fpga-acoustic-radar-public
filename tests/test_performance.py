import unittest
from types import SimpleNamespace

from radar.performance import PerformanceTrace


class PerformanceTraceTest(unittest.TestCase):
    def setUp(self):
        self.trace = PerformanceTrace()

    def frame(self, seq, t, level, angle, gated=False, source="L"):
        self.trace.observe(SimpleNamespace(source=source, sequence=seq), t, level,
                           angle, False, gated)

    def test_attack_can_wait_for_confirmation_without_repeating_on_sustain(self):
        self.frame(1, 0, -45, None, gated=True)
        self.frame(2, .1, -13, None)
        self.frame(3, .2, -18, 90)
        self.frame(3, .21, -11, 90)
        self.frame(4, .3, -19, 92)
        self.assertEqual([(m.time, m.angle) for m in self.trace.arcs], [(.1, 90)])
        self.assertEqual(len(self.trace.history), 4)
        self.frame(5, .4, -9, 120)
        self.assertEqual(self.trace.arcs[-1].angle, 120)
        self.assertGreater(self.trace.arcs[-1].strength, self.trace.arcs[0].strength)
        self.frame(6, .6, -60, None, gated=True)
        self.assertFalse(self.trace.arcs)
        self.assertIsNone(self.trace.history[-1].angle)
        self.frame(7, .7, -15, 270)
        self.assertEqual(self.trace.trail_start, .7)
        self.assertEqual([m.angle for m in self.trace.arcs], [270])

    def test_expiry_source_reset_and_unresolved_attack(self):
        for i in range(70):
            self.frame(i, i * .1, -16, None if i <= 5 else 45)
        self.assertFalse(self.trace.arcs)
        self.assertGreaterEqual(self.trace.history[0].time, 1.9)
        self.frame(1, 7.1, -9, 180, source="D")
        self.assertEqual(len(self.trace.history), 1)
        self.frame(2, 8.4, -11, 0, source="D")
        self.assertEqual(len(self.trace.history), 1)
        self.trace.reset()
        self.assertFalse(self.trace.arcs)
        self.assertFalse(self.trace.history)
