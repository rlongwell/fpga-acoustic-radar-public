"""Short visual history derived from timestamped radar windows."""
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Mark:
    time: float
    angle: int | None
    approximate: bool
    strength: float


class PerformanceTrace:
    duration = 5.0
    arc_lifetime = 1.15

    def __init__(self):
        self.history = deque()
        self.arcs = deque()
        self.reset()

    def reset(self):
        self.history.clear()
        self.quiet()
        self.last_key = None

    def quiet(self):
        self.arcs.clear()
        self.trail_start = float("inf")
        self.pending_attack = None
        self.previous_level = None
        self.last_attack = float("-inf")

    def observe(self, frame, time, level, angle, approximate, gated):
        key = (frame.source, frame.sequence)
        if key == self.last_key:
            return
        if self.last_key and (key[0] != self.last_key[0] or key[1] < self.last_key[1]
                              or time - self.history[-1].time >= 1.0):
            self.reset()
        self.last_key = key
        while self.history and time - self.history[0].time > self.duration:
            self.history.popleft()
        while self.arcs and time - self.arcs[0].time >= self.arc_lifetime:
            self.arcs.popleft()
        strength = min(1.0, max(0.0, (level + 48) / 48))
        self.history.append(Mark(time, None if gated else angle, approximate, strength))
        if gated:
            self.quiet()
            return
        self.trail_start = min(self.trail_start, time)
        rising = self.previous_level is None or level - self.previous_level >= 4
        if rising and time - self.last_attack >= 0.18:
            self.pending_attack = (time, strength)
            self.last_attack = time
        self.previous_level = level
        if self.pending_attack:
            onset, brightness = self.pending_attack
            if time - onset > 0.35:
                self.pending_attack = None
            elif angle is not None:
                # The reflection filter may confirm direction one window after the attack.
                self.arcs.append(Mark(onset, angle, approximate, brightness))
                self.pending_attack = None
