"""Low-frequency and competing-bearing regressions for Gentle mode."""
import math
import unittest
from dataclasses import replace

from radar.localization import RATE, SPEED, ReflectionTracker, Solver, angle_distance
from radar.protocol import BINS, MAX_LAG, PAIRS, WINDOW


def tone(solver, frequency, angle, sequence=1):
    phi = math.radians(angle)
    arrivals = [-(x * math.sin(phi) + y * math.cos(phi)) * RATE / SPEED for x, y in solver.positions]
    scores = tuple(round(110 * math.cos(2 * math.pi * frequency * (lag - (arrivals[b] - arrivals[a])) / RATE))
                   for a, b in PAIRS for lag in range(-MAX_LAG, MAX_LAG + 1))
    return replace(solver.demo(angle, sequence), source="L", scores=scores, energy=(WINDOW * 1000,) * 6)


class GentleTest(unittest.TestCase):
    def setUp(self):
        self.solver = Solver(36, 55)
        self.tracker = ReflectionTracker("gentle")

    def update(self, frame):
        result = self.solver.estimate(frame, strength="gentle")
        return self.tracker.update(frame, result, now=frame.sequence * 0.2)

    def direct(self, angle, sequence):
        return replace(self.solver.demo(angle, sequence), source="L", energy=(WINDOW * 1000,) * 6)

    def test_hum_is_visible_and_plateau_is_centered(self):
        for frequency in (100, 150, 200, 300, 500):
            for angle in (0, 40, 90, 220, 359):
                with self.subTest(frequency=frequency, angle=angle):
                    frame = tone(self.solver, frequency, angle)
                    self.assertFalse(self.solver.estimate(frame).valid)
                    result = self.solver.estimate(frame, strength="gentle")
                    self.assertTrue(result.valid, result.reason)
                    self.assertLessEqual(angle_distance(result.angle, angle), 7)
                    if frequency <= 200:
                        self.assertTrue(result.uncertain)

    def test_hum_with_mic_two_silent(self):
        frame = tone(self.solver, 150, 40)
        result = self.solver.estimate(replace(frame, energy=(WINDOW * 1000, 0) + (WINDOW * 1000,) * 4), strength="gentle")
        self.assertTrue(result.valid)
        self.assertEqual(result.usable_pairs, 10)
        self.assertLessEqual(angle_distance(result.angle, 40), 7)

    def test_marginal_opposite_peak_does_not_steal_track(self):
        self.update(self.direct(40, 1))
        self.assertTrue(self.update(self.direct(40, 2)).valid)
        for sequence in range(3, 10):
            a, b = self.direct(40, sequence), self.direct(220, sequence)
            frame = replace(a, scores=tuple(round((x + 1.05 * y) / 2.05) for x, y in zip(a.scores, b.scores)))
            result = self.update(frame)
            self.assertTrue(result.valid, result.reason)
            self.assertTrue(result.uncertain)
            self.assertLessEqual(angle_distance(result.angle, 40), 8)

    def test_real_opposite_move_reacquires_after_four_frames(self):
        self.update(self.direct(40, 1))
        self.update(self.direct(40, 2))
        for sequence in (3, 4, 5):
            self.assertFalse(self.update(self.direct(220, sequence)).valid)
        result = self.update(self.direct(220, 6))
        self.assertTrue(result.valid)
        self.assertLessEqual(angle_distance(result.angle, 220), 7)

    def test_falling_volume_alone_does_not_hide_gentle_source(self):
        for sequence in (1, 2):
            self.update(replace(self.direct(40, sequence), energy=(WINDOW * 10000,) * 6))
        result = self.update(replace(self.direct(40, 3), energy=(WINDOW * 100,) * 6))
        self.assertTrue(result.valid)

    def test_flat_field_and_silence_still_have_no_direction(self):
        frame = self.direct(40, 1)
        flat = replace(frame, scores=(110,) * (len(PAIRS) * BINS))
        result = self.solver.estimate(flat, strength="gentle")
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "Sound detected; direction unresolved")
        self.update(frame)
        self.update(self.direct(40, 2))
        silent = replace(self.direct(40, 3), energy=(0,) * 6, scores=(0,) * (len(PAIRS) * BINS))
        self.assertFalse(self.update(silent).valid)


if __name__ == "__main__":
    unittest.main()
