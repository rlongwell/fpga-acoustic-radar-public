"""ASCII UART frames from the Zybo Linux bridge."""
import base64
import struct
import zlib
from dataclasses import dataclass, replace

PAIRS = tuple((a, b) for a in range(6) for b in range(a + 1, 6))
MAX_LAG = 32
BINS = 2 * MAX_LAG + 1
WINDOW = 4096

# GUI mic number -> zero-based FPGA input. The harness is at the upper right.
FPGA_INPUTS = tuple(range(6))
FPGA_JE = (7, 4, 3, 8, 9, 10)
HEX_INPUTS = (3, 4, 5, 0, 1, 2)
HEX_PORT_ORDER = "clockwise-from-je8"


def _hex_score_indices():
    indices = []
    for a, b in PAIRS:
        first, second = HEX_INPUTS[a], HEX_INPUTS[b]
        pair = PAIRS.index(tuple(sorted((first, second))))
        block = range(pair * BINS, (pair + 1) * BINS)
        # Cross-correlation lag changes sign when the two inputs exchange roles.
        indices.extend(block if first < second else reversed(block))
    return tuple(indices)


_HEX_SCORE_INDICES = _hex_score_indices()


@dataclass(frozen=True)
class Frame:
    source: str
    sequence: int
    samples: int
    dropped: int
    energy: tuple
    scores: tuple

    def in_hex_order(self):
        return replace(self, energy=tuple(self.energy[i] for i in HEX_INPUTS),
                       scores=tuple(self.scores[i] for i in _HEX_SCORE_INDICES))

    @classmethod
    def parse(cls, line):
        content, check = line.rstrip(b"\r\n").rsplit(b" ", 1)
        if len(check) != 8 or zlib.crc32(content) != int(check, 16):
            raise ValueError("Radar frame checksum mismatch")
        tag, source, sequence, samples, dropped, energy, data = content.split(b" ")
        if tag != b"AR1" or source not in (b"L", b"T"):
            raise ValueError("Unknown radar frame format")
        powers = tuple(map(int, energy.split(b",")))
        raw = base64.b64decode(data, validate=True)
        if len(powers) != 6 or any(p < 0 or p > 2**30 for p in powers) or len(raw) != len(PAIRS) * BINS:
            raise ValueError("Invalid radar payload length or energy")
        scores = struct.unpack(f"{len(raw)}b", raw)
        return cls(source.decode(), int(sequence), int(samples), int(dropped), powers, scores)
