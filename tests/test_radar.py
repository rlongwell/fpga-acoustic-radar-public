import base64
import struct
import unittest
import zlib
from dataclasses import replace

from radar.localization import Solver
from radar.protocol import BINS, PAIRS, Frame


class RadarTest(unittest.TestCase):
    def test_uart_frame_and_crc(self):
        source = Solver(50, 100).demo(75, 1)
        packed = base64.b64encode(struct.pack(f"{len(source.scores)}b", *source.scores))
        body = b"AR1 L 1 8290 0 " + ",".join(map(str, source.energy)).encode() + b" " + packed
        packet = body + f" {zlib.crc32(body):08x}\r\n".encode()
        decoded = Frame.parse(packet)
        self.assertEqual(decoded.scores, source.scores)
        self.assertEqual(decoded.source, "L")
        with self.assertRaises(ValueError):
            Frame.parse(packet.replace(b"8290", b"8291"))

    def test_bearings_and_silence(self):
        solver = Solver(50, 100)
        for angle in (2, 48, 98, 172, 240, 307, 359):
            with self.subTest(angle=angle):
                estimate = solver.estimate(solver.demo(angle, 1))
                self.assertTrue(estimate.valid)
                self.assertLessEqual(min((estimate.angle - angle) % 360, (angle - estimate.angle) % 360), 5)
        silence = Frame("L", 1, 8290, 0, (0,) * 6, (0,) * 975)
        self.assertFalse(solver.estimate(silence).valid)
        with self.assertRaises(ValueError):
            Solver(150, 150)

    def test_bearing_with_mic_two_silent(self):
        solver = Solver(50, 100)
        source = solver.demo(75, 1)
        energy = list(source.energy)
        energy[1] = 0
        scores = list(source.scores)
        for pair, mics in enumerate(PAIRS):
            if 1 in mics:
                scores[pair * BINS:(pair + 1) * BINS] = [-127] * BINS
        result = solver.estimate(replace(source, source="L", energy=tuple(energy), scores=tuple(scores)))
        self.assertTrue(result.valid)
        self.assertLessEqual(abs(result.angle - 75), 5)
        self.assertEqual(result.active_channels, (0, 2, 3, 4, 5))
        self.assertEqual(len(result.curve), 360)


if __name__ == "__main__":
    unittest.main()
