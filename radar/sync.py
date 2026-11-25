"""Relate the FPGA sample clock to the PC clock for video editing."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import struct


@dataclass(frozen=True)
class TakeClock:
    start_local: datetime
    uncertainty_ms: float

    @classmethod
    def from_packet(cls, go_utc_ns, elapsed_ns, samples, rate):
        # Sample zero follows GO. The final sample already exists when its
        # packet reaches the PC. Remove its known sample span from the bracket.
        width_ns = max(0, elapsed_ns - (samples - 1) * 1_000_000_000 // rate)
        midpoint_ns = go_utc_ns + width_ns // 2
        seconds, nanos = divmod(midpoint_ns, 1_000_000_000)
        utc = datetime.fromtimestamp(seconds, timezone.utc) + timedelta(microseconds=nanos // 1000)
        return cls(utc.astimezone(), width_ns / 2_000_000)

    def metadata(self):
        return {"first_sample_local": self.start_local.isoformat(timespec="microseconds"),
                "first_sample_utc": self.start_local.astimezone(timezone.utc).isoformat(timespec="microseconds"),
                "pc_bracket_half_width_ms": round(self.uncertainty_ms, 3)}

    @classmethod
    def load(cls, data):
        start = datetime.fromisoformat(data["first_sample_local"])
        if start.utcoffset() is None:
            raise ValueError("Take start time needs a UTC offset")
        return cls(start, float(data["pc_bracket_half_width_ms"]))

    def ticks_since_midnight(self, rate):
        t = self.start_local
        return ((t.hour * 60 + t.minute) * 60 + t.second) * rate + t.microsecond * rate // 1_000_000

    def timecode(self, fps):
        frame = self.ticks_since_midnight(fps) % fps
        return f"{self.start_local:%H:%M:%S}:{frame:02d}"


@contextmanager
def broadcast_wave(path, channels, rate, clock):
    """Write packed PCM with a BWF v0 bext chunk before the audio data."""
    start = clock.start_local
    description = b"Zybo M1" if channels == 1 else b"Zybo M1 through M6"
    bext = struct.pack("<256s32s32s10s8sQH254x", description, b"Acoustic Radar", b"",
                       start.strftime("%Y-%m-%d").encode(), start.strftime("%H:%M:%S").encode(),
                       clock.ticks_since_midnight(rate), 0)
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * channels * 3, channels * 3, 24)
    with path.open("xb") as file:
        file.write(b"RIFF\0\0\0\0WAVE")
        for name, chunk in ((b"bext", bext), (b"fmt ", fmt)):
            file.write(struct.pack("<4sI", name, len(chunk)))
            file.write(chunk)
        file.write(b"data\0\0\0\0")
        data_start = file.tell()
        try:
            yield file
        finally:
            size = file.tell() - data_start
            if size % 2:
                file.write(b"\0")
            riff_size = file.tell() - 8
            file.seek(data_start - 4)
            file.write(struct.pack("<I", size))
            file.seek(4)
            file.write(struct.pack("<I", riff_size))
