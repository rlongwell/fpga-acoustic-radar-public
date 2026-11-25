"""Emulate swapped SD leads without changing the physical source direction."""
import unittest
from dataclasses import replace

from radar.localization import Solver, angle_distance
from radar.protocol import BINS, PAIRS


def swap_frame_channels(frame):
    # New channel -> original physical microphone. Reversing a pair also
    # reverses its lag axis, which matters for the 4/5 cross-correlation.
    order = (0, 1, 2, 4, 3, 5)
    scores = []
    for a, b in PAIRS:
        first, second = order[a], order[b]
        pair = PAIRS.index(tuple(sorted((first, second))))
        bins = frame.scores[pair * BINS:(pair + 1) * BINS]
        scores.extend(bins if first < second else bins[::-1])
    return replace(frame, energy=tuple(frame.energy[i] for i in order), scores=tuple(scores))


class ChannelMappingTest(unittest.TestCase):
    def test_swapped_leads_recover_different_source_directions(self):
        normal = Solver(36, 55)
        mapped = Solver(36, 55, swap_mic4_mic5=True)
        for angle in (0, 45, 90, 180, 270, 359):
            with self.subTest(angle=angle):
                frame = swap_frame_channels(normal.demo(angle, 1))
                frame = replace(frame, energy=(frame.energy[0], 0) + frame.energy[2:])
                result = mapped.estimate(frame, reject_reflections=False)
                self.assertTrue(result.valid)
                self.assertLessEqual(angle_distance(result.angle, angle), 5)

    def test_default_mapping_still_recovers_normal_leads(self):
        solver = Solver(36, 55)
        for angle in (90, 270):
            result = solver.estimate(solver.demo(angle, 1), reject_reflections=False)
            self.assertTrue(result.valid)
            self.assertLessEqual(angle_distance(result.angle, angle), 5)


if __name__ == "__main__":
    unittest.main()
