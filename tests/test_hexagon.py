"""Check hexagon coordinates, lag polarity and angles independently of the solver's demo."""
import math
import unittest

from radar.localization import HEX_PORTS_MM, Solver, angle_distance
from radar.protocol import Frame, MAX_LAG, PAIRS


class HexagonTest(unittest.TestCase):
    def test_physical_grid_and_lag_sign(self):
        solver = Solver()
        holes = ((28, 14), (46, 14), (55, 29), (46, 44), (28, 44), (19, 29))
        for (x, y), (col, row) in zip(solver.positions, holes):
            self.assertAlmostEqual(x, (col - 37) * 0.00254)
            self.assertAlmostEqual(y, (29 - row) * 0.00254)
        m3_m6 = PAIRS.index((2, 5))
        self.assertAlmostEqual(solver.delays(0)[m3_m6], 0.09144 * 48000 / 343)
        self.assertAlmostEqual(solver.delays(180)[m3_m6], -0.09144 * 48000 / 343)
        self.assertAlmostEqual(solver.delays(270)[PAIRS.index((1, 3))], -0.07620 * 48000 / 343)
        self.assertAlmostEqual(solver.delays(270)[PAIRS.index((3, 4))], 0)

    def test_bearings_from_independent_arrival_times(self):
        # Source positions are 10 m from the center. Compute exact spherical
        # propagation times to the ports, including integer-lag interpolation.
        solver = Solver()
        for degrees in (0, 30, 60, 90, 120, 180, 225, 240, 270, 300, 359):
            phi = math.radians(degrees)
            source = (10000 * math.cos(phi), 10000 * math.sin(phi))
            arrivals = [math.dist(p, source) * 48 / 343 for p in HEX_PORTS_MM]
            scores = tuple(round(120 * math.exp(-0.5 * (lag - (arrivals[b] - arrivals[a]))**2))
                           for a, b in PAIRS for lag in range(-MAX_LAG, MAX_LAG + 1))
            frame = Frame("L", 1, 4096, 0, (4000000,) * 6, scores)
            for filtered in (False, True):
                result = solver.estimate(frame, reject_reflections=filtered, strength="gentle")
                self.assertTrue(result.valid)
                self.assertLessEqual(angle_distance(result.angle, degrees), 3)

    def test_temperature_and_coordinate_calibration(self):
        nominal = Solver()
        warm = Solver(temperature_c=35)
        pair = PAIRS.index((2, 5))
        self.assertAlmostEqual(nominal.speed, 343.0)
        self.assertLess(warm.delays(0)[pair], nominal.delays(0)[pair])
        ports = HEX_PORTS_MM[:2] + ((46.72, 0),) + HEX_PORTS_MM[3:]
        self.assertAlmostEqual(Solver(ports_mm=ports).delays(0)[pair] - nominal.delays(0)[pair], 48 / 343)
        with self.assertRaises(ValueError):
            Solver(ports_mm=((0, 0),) * 6)
        with self.assertRaises(ValueError):
            Solver(ports_mm=((300, 0),) + HEX_PORTS_MM[1:])


if __name__ == "__main__":
    unittest.main()
