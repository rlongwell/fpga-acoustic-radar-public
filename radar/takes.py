"""Radar takes, aligned to the same FPGA sample counter as the microphone WAVs."""
import base64
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import struct
import time
import wave

from .localization import Bearing
from .pcm import CHANNELS, RATE, sample_delta
from .sync import TakeClock
from .performance import Mark

TAKES = Path.home() / "Videos" / "Acoustic Radar"
FORMAT = {"format": "acoustic-radar-take", "version": 1}


def saved_bearing(result):
    if result is None:
        return None
    return {"angle": result.angle, "valid": result.valid,
            "curve": [round(value, 5) for value in result.curve]}


def loaded_bearing(data):
    if data is None:
        return None
    curve = tuple(data["curve"])
    if len(curve) not in (0, 360) or not all(math.isfinite(v) for v in curve):
        raise ValueError("Invalid recorded direction curve")
    return Bearing(int(data["angle"]) % 360, 0, 0, bool(data["valid"]), curve, ())


class TakeWriter:
    def __init__(self, root=TAKES):
        self.path = root / datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        self.path.mkdir(parents=True)
        self.file = (self.path / "take.jsonl").open("x", encoding="utf-8")
        self.write(FORMAT)

    def write(self, data):
        self.file.write(json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n")
        self.file.flush()

    def capture(self, polar, label, frame):
        now = time.monotonic()
        arcs = [[round(now - arc.time, 4), arc.angle, arc.strength]
                for arc in polar.trace.arcs if now - arc.time < polar.trace.arc_lifetime]
        dots = [[round(now - pt.time, 4), pt.angle, pt.strength]
                for pt in polar.trace.history
                if pt.angle is not None and now - pt.time <= 1.6 and pt.time >= polar.trace.trail_start]
        scores = struct.pack(f"{len(frame.scores)}b", *frame.scores)
        self.write(dict(samples=frame.samples, sequence=frame.sequence, dropped=frame.dropped,
                        energy=frame.energy, scores_b64=base64.b64encode(scores).decode("ascii"),
                        text=label, ports=polar.mic_positions, hex=polar.ports_mm is not None,
                        levels=polar.mic_levels, result=saved_bearing(polar.result), raw=saved_bearing(polar.raw_result),
                        filtered=polar.filtered, provisional=polar.provisional, arcs=arcs, dots=dots))

    def finish(self, audio, error=""):
        try:
            self.write(dict(end=True, first_sample=audio.first, audio_frames=audio.frames, error=error,
                            fpga_channels=[i + 1 for i in audio.channel_order],
                            clock=audio.clock.metadata() if audio.clock else None))
        finally:
            self.file.close()


@dataclass
class Take:
    frames: list
    times: list
    duration: float
    path: Path
    error: str
    clock: TakeClock | None = None

    @classmethod
    def load(cls, path):
        path = Path(path)
        frames = []
        footer = {}
        with path.open(encoding="utf-8") as file:
            if json.loads(file.readline()) != FORMAT:
                raise ValueError("Unknown radar take format")
            for line in file:
                row = json.loads(line)
                if row.get("end"):
                    footer = row
                    break
                row.pop("scores_b64", None)
                ports = [(float(x), float(y)) for x, y in row["ports"]]
                if len(ports) != 6 or len(set(ports)) != 6 or not all(math.isfinite(v) for p in ports for v in p):
                    raise ValueError("Invalid recorded array geometry")
                if len(row["levels"]) != 6 or not all(math.isfinite(v) for v in row["levels"]):
                    raise ValueError("Invalid microphone levels")
                row["result"] = loaded_bearing(row["result"])
                row["raw"] = loaded_bearing(row["raw"])
                frames.append(row)
        if not footer.get("audio_frames") or footer.get("first_sample") is None:
            raise ValueError(footer.get("error") or "No finalized Zybo audio in this take")
        with wave.open(str(path.parent / "guitar.wav")) as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getnframes()) != (
                    1, 3, RATE, footer["audio_frames"]):
                raise ValueError("Audio length or format differs from the radar take")
        duration = footer["audio_frames"] / RATE
        for row in frames:
            row["t"] = sample_delta(row["samples"], footer["first_sample"]) / RATE
        frames = [r for r in frames if 0 <= r["t"] <= duration]
        times = [r["t"] for r in frames]
        if times != sorted(times):
            raise ValueError("The FPGA sample counter restarted during this take")
        clock = TakeClock.load(footer["clock"]) if footer.get("clock") else None
        return cls(frames, times, duration, path, footer["error"], clock)

    def audio_path(self, source):
        if source == "m1":
            return self.path.parent / "guitar.wav"
        if source != "all":
            raise ValueError("Unknown replay audio source")
        path = self.path.parent / "microphones.wav"
        with wave.open(str(path)) as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getnframes()) != (
                    CHANNELS, 3, RATE, round(self.duration * RATE)):
                raise ValueError("Six-channel WAV differs from the radar take")
            audio.setpos(audio.getnframes() - 1)
            if len(audio.readframes(1)) != CHANNELS * 3:
                raise ValueError("Six-channel WAV is incomplete")
        return path

    def frame_at(self, position):
        index = bisect_right(self.times, position) - 1
        if index < 0 or position - self.times[index] > 1:
            return None
        return self.frames[index]

    @staticmethod
    def apply(polar, frame, position):
        polar.playback_time = position
        polar.trace.reset()
        polar.result = polar.raw_result = None
        polar.mic_levels = [-60] * 6
        if frame is not None:
            polar.ports_mm = frame["ports"] if frame["hex"] else None
            polar.mic_positions = frame["ports"]
            polar.filtered = frame["filtered"]
            polar.provisional = frame["provisional"]
            polar.mic_levels = frame["levels"]
            polar.result, polar.raw_result = frame["result"], frame["raw"]
            for age, angle, strength in frame["arcs"]:
                polar.trace.arcs.append(Mark(frame["t"]-age, angle, False, strength))
            polar.trace.trail_start = float("-inf")
            for age, angle, strength in frame["dots"]:
                polar.trace.history.append(Mark(frame["t"]-age, angle, False, strength))
        polar.update()
