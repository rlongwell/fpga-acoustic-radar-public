"""Synthetic regression cases; these do not establish room accuracy."""
import math
import random
import unittest
from dataclasses import replace

from radar.localization import RATE, SPEED, ReflectionTracker, Solver, angle_distance
from radar.protocol import BINS, MAX_LAG, PAIRS, WINDOW, Frame


def waveform_echo(solver, angle=40, echo_angle=215, echo_gain=0.55):
    """Same broadband source arrives directly and again 6.25 ms later.

    Build six sampled waveforms first, then estimate the bounded normalized
    correlations the UART exposes. No solver.demo/angle-score construction.
    """
    rng = random.Random(901)
    source = [rng.gauss(0, 45) for _ in range(WINDOW + 1100)]

    def sample(t):
        n = math.floor(t)
        return source[n] * (1 - (t - n)) + source[n + 1] * (t - n)

    channels = []
    for x, y in solver.positions:
        direct = -(x * math.sin(math.radians(angle)) + y * math.cos(math.radians(angle))) * RATE / SPEED
        echo = 300 - (x * math.sin(math.radians(echo_angle)) + y * math.cos(math.radians(echo_angle))) * RATE / SPEED
        channels.append([round(sample(t + 500 - direct) + echo_gain * sample(t + 500 - echo) + rng.gauss(0, 2))
                         for t in range(WINDOW + 2 * MAX_LAG)])
    energy = tuple(sum(v * v for v in channel[MAX_LAG:MAX_LAG + WINDOW]) for channel in channels)
    scores = []
    for a, b in PAIRS:
        scale = math.sqrt(energy[a] * energy[b])
        for lag in range(-MAX_LAG, MAX_LAG + 1):
            value = sum(channels[a][t - lag] * channels[b][t] for t in range(MAX_LAG, MAX_LAG + WINDOW))
            scores.append(max(-127, min(127, round(127 * value / scale))))
    return Frame("L", 1, WINDOW, 0, energy, tuple(scores))


class ReflectionTest(unittest.TestCase):
    def setUp(self):
        self.solver = Solver(36, 55)
        self.tracker = ReflectionTracker()

    def frame(self, angle, sequence, power=1000):
        frame = self.solver.demo(angle, sequence)
        return replace(frame, source="L", energy=(WINDOW * power,) * 6)

    def update(self, angle, sequence, power=1000, now=None):
        frame = self.frame(angle, sequence, power)
        return self.tracker.update(frame, self.solver.estimate(frame), now=sequence * 0.2 if now is None else now)

    def test_direct_plus_delayed_same_source(self):
        for gain in (0.0, 0.55):
            with self.subTest(echo_gain=gain):
                result = self.solver.estimate(waveform_echo(self.solver, echo_gain=gain))
                self.assertTrue(result.valid, result)
                self.assertLessEqual(angle_distance(result.angle, 40), 6)

    def test_two_equal_competing_directions_rejected(self):
        a, b = self.frame(40, 1), self.frame(215, 1)
        mixed = replace(a, scores=tuple(round((x + y) / 2) for x, y in zip(a.scores, b.scores)))
        result = self.solver.estimate(mixed)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "Competing or broad directions")

    def test_equal_direct_and_echo_waveforms_are_ambiguous(self):
        result = self.solver.estimate(waveform_echo(self.solver, echo_gain=1.0))
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "Competing or broad directions")

    def test_pair_outliers_do_not_steer_majority(self):
        direct, echo = self.frame(40, 1), self.frame(215, 1)
        scores = list(direct.scores)
        for pair in (0, 5, 12):
            scores[pair * BINS:(pair + 1) * BINS] = echo.scores[pair * BINS:(pair + 1) * BINS]
        result = self.solver.estimate(replace(direct, scores=tuple(scores)))
        self.assertTrue(result.valid)
        self.assertLessEqual(angle_distance(result.angle, 40), 6)

    def test_flat_correlated_and_uncorrelated_noise_rejected(self):
        frame = self.frame(40, 1)
        rng = random.Random(7)
        for scores in ((75,) * (15 * BINS), tuple(rng.randrange(-12, 13) for _ in frame.scores)):
            self.assertFalse(self.solver.estimate(replace(frame, scores=scores)).valid)

    def test_small_array_silent_mic_two(self):
        frame = self.frame(75, 1)
        scores = list(frame.scores)
        for pair, mics in enumerate(PAIRS):
            if 1 in mics:
                scores[pair * BINS:(pair + 1) * BINS] = [-127] * BINS
        result = self.solver.estimate(replace(frame, energy=(WINDOW * 1000, 0) + (WINDOW * 1000,) * 4,
                                              scores=tuple(scores)))
        self.assertTrue(result.valid)
        self.assertEqual(result.usable_pairs, 10)
        self.assertLessEqual(angle_distance(result.angle, 75), 6)

    def test_confirmation_and_one_frame_direction_jump(self):
        self.assertFalse(self.update(40, 1).valid)
        self.assertTrue(self.update(40, 2).valid)
        jump = self.update(215, 3)
        self.assertFalse(jump.valid)
        self.assertEqual(jump.reason, "Checking new direction")
        self.assertTrue(self.update(40, 4).valid)

    def test_sustained_new_direction_is_acquired(self):
        self.update(40, 1)
        self.update(40, 2)
        self.assertFalse(self.update(215, 3).valid)
        self.assertFalse(self.update(215, 4).valid)
        result = self.update(215, 5)
        self.assertTrue(result.valid)
        self.assertLessEqual(angle_distance(result.angle, 215), 6)

    def test_fading_tail_is_suppressed_and_quieter_source_can_recover(self):
        self.update(40, 1, 10000)
        self.update(40, 2, 10000)
        result = self.update(215, 3, 500)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "Fading sound suppressed")
        for sequence in range(4, 20):
            result = self.update(215, sequence, 500)
        self.assertTrue(result.valid)

    def test_clean_short_onset_can_be_seen(self):
        quiet = replace(self.frame(40, 1, 1), scores=(0,) * (15 * BINS))
        self.tracker.update(quiet, self.solver.estimate(quiet), now=0.2)
        self.assertTrue(self.update(40, 2, 10000).valid)

    def test_duplicates_dont_confirm_and_gap_resets(self):
        first = self.update(40, 1)
        for _ in range(4):
            self.assertEqual(self.update(40, 1), first)
        self.assertTrue(self.update(40, 2).valid)
        self.assertFalse(self.update(40, 3, now=2.0).valid)

    def test_restart_or_source_change_resets(self):
        self.update(40, 1)
        self.update(40, 2)
        self.assertFalse(self.update(40, 1, now=0.6).valid)
        self.update(40, 2, now=0.8)
        demo = self.solver.demo(40, 3)
        self.assertFalse(self.tracker.update(demo, self.solver.estimate(demo), now=1.0).valid)

    def test_wraparound_smoothing(self):
        self.update(355, 1)
        self.update(355, 2)
        result = self.update(5, 3)
        self.assertTrue(result.valid)
        self.assertLessEqual(angle_distance(result.angle, 0), 6)

    def test_no_marker_on_silence_or_ambiguity(self):
        self.update(40, 1)
        self.update(40, 2)
        silent = replace(self.frame(40, 3), energy=(0,) * 6, scores=(0,) * (15 * BINS))
        self.assertFalse(self.tracker.update(silent, self.solver.estimate(silent), now=0.6).valid)

    def test_coherent_reflection_is_an_explicit_limit(self):
        # A single persistent wavefront has no direct/reflected identity in
        # bounded pair correlations. Do not claim that this case is rejected.
        self.assertFalse(self.update(215, 1).valid)
        self.assertTrue(self.update(215, 2).valid)


if __name__ == "__main__":
    unittest.main()
