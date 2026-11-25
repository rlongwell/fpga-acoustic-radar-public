"""Project the FPGA's pair correlations onto horizontal far-field bearings."""
import math
import statistics
import time
from dataclasses import dataclass, replace
from .protocol import BINS, MAX_LAG, PAIRS, WINDOW, Frame

RATE = 48_000
SPEED = 343.0
# Coordinates in GUI order, clockwise from upper left in the current viewing orientation.
HEX_PORTS_MM = ((-22.86, 38.10), (22.86, 38.10), (45.72, 0.0),
                (22.86, -38.10), (-22.86, -38.10), (-45.72, 0.0))
HEX_LOCATIONS = ("Upper left", "Upper right", "Right", "Lower right", "Lower left", "Left")


def sound_speed(temperature_c):
    if not math.isfinite(temperature_c) or not -40 <= temperature_c <= 60:
        raise ValueError("Enter an air temperature between -40 and 60 °C")
    return SPEED * math.sqrt((273.15 + temperature_c) / 293.15)


def bearing_vector(angle, xy_angles):
    phi = math.radians(angle if xy_angles else 90 - angle)
    return math.cos(phi), math.sin(phi)


def hex_ports_mm(values):
    try:
        points = tuple((float(x), float(y)) for x, y in values)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Enter six acoustic-port X/Y coordinates") from error
    if len(points) != 6 or len(set(points)) != 6 or not all(math.isfinite(v) for p in points for v in p):
        raise ValueError("Enter six distinct, finite port coordinates")
    ax, ay = points[0]
    bx, by = points[1]
    if all(abs((bx-ax)*(cy-ay) - (by-ay)*(cx-ax)) < 0.01 for cx, cy in points[2:]):
        raise ValueError("The acoustic ports must span two dimensions")
    return points


@dataclass(frozen=True)
class Bearing:
    angle: int
    correlation: float
    prominence: float
    valid: bool
    curve: tuple
    active_channels: tuple
    agreement: float = 0.0
    supporting_pairs: int = 0
    usable_pairs: int = 0
    reason: str = ""
    uncertain: bool = False
    pair_counts: tuple = ()


def angle_distance(a, b):
    return abs((a - b + 180) % 360 - 180)


def positions(column_mm, row_mm):
    if not math.isfinite(column_mm) or not math.isfinite(row_mm) or min(column_mm, row_mm) <= 0:
        raise ValueError("Enter two positive spacings")
    return tuple(((column - 1) * column_mm / 1000, (0.5 - row) * row_mm / 1000)
                 for row in range(2) for column in range(3))


class Solver:
    def __init__(self, column_mm=None, row_mm=None, swap_mic4_mic5=False, *,
                 ports_mm=None, temperature_c=20.0):
        self.speed = sound_speed(temperature_c)
        self.xy_angles = column_mm is None and row_mm is None
        if self.xy_angles:
            if swap_mic4_mic5:
                raise ValueError("The MIC4/5 wiring override is for the rectangular array")
            points = hex_ports_mm(HEX_PORTS_MM if ports_mm is None else ports_mm)
            self.positions = tuple((x / 1000, y / 1000) for x, y in points)
        else:
            if column_mm is None or row_mm is None or ports_mm is not None:
                raise ValueError("Specify both rectangular spacings or six X/Y coordinates")
            points = list(positions(column_mm, row_mm))
            if swap_mic4_mic5:
                points[3], points[4] = points[4], points[3]
            self.positions = tuple(points)
        max_distance = max(math.dist(self.positions[a], self.positions[b]) for a, b in PAIRS)
        if max_distance * RATE / self.speed > MAX_LAG:
            raise ValueError("Port spacing exceeds the FPGA's ±32-sample lag range")
        self.lags = [self.delays(angle) for angle in range(360)]

    def delays(self, angle):
        dx, dy = bearing_vector(angle, self.xy_angles)
        return tuple(-((self.positions[b][0] - self.positions[a][0]) * dx +
                       (self.positions[b][1] - self.positions[a][1]) * dy) * RATE / self.speed
                     for a, b in PAIRS)

    def estimate(self, frame, reject_reflections=True, strength="strong"):
        gentle = reject_reflections and strength == "gentle"
        active = tuple(i for i, power in enumerate(frame.energy) if power >= WINDOW * 4)
        plane = any(abs((self.positions[b][0] - self.positions[a][0]) *
                        (self.positions[c][1] - self.positions[a][1]) -
                        (self.positions[b][1] - self.positions[a][1]) *
                        (self.positions[c][0] - self.positions[a][0])) > 1e-8
                    for a in active for b in active for c in active if a < b < c)
        usable = [k for k, (a, b) in enumerate(PAIRS) if a in active and b in active]
        if not plane:
            return Bearing(0, 0, 0, False, (), active, reason="Need three active, non-collinear mics")
        # Bound each pair's evidence to physically possible propagation delays.
        # Normalize peak contrast per pair so a few strong pairs cannot dominate.
        profiles = {}
        for pair in usable:
            a, b = PAIRS[pair]
            extent = min(MAX_LAG, math.ceil(math.dist(self.positions[a], self.positions[b]) * RATE / self.speed))
            bins = frame.scores[pair * BINS + MAX_LAG - extent:pair * BINS + MAX_LAG + extent + 1]
            baseline = statistics.median(bins) / 127
            contrast = max(bins) / 127 - baseline
            profiles[pair] = (baseline, contrast)
        curve = []
        correlations = []
        support = []
        for lags in self.lags:
            total = 0.0
            evidence = []
            supporting = []
            for pair in usable:
                bin_position = min(MAX_LAG * 2, max(0.0, lags[pair] + MAX_LAG))
                low = int(bin_position)
                fraction = bin_position - low
                first = pair * BINS + low
                second = pair * BINS + min(low + 1, BINS - 1)
                value = (frame.scores[first] * (1.0 - fraction) + frame.scores[second] * fraction) / 127
                total += value
                baseline, contrast = profiles[pair]
                relative = max(0.0, min(1.0, (value - baseline) / max(contrast, 0.08)))
                if contrast < 0.08 or value < 0.08:
                    relative = 0.0
                evidence.append(relative)
                # Broad tonal peaks may have little contrast on a small array.
                # Gentle mode uses proximity to the pair peak, retaining an
                # absolute correlation floor instead of requiring sharpness.
                # The FPGA reports integer lags. At a fractional delay a clean,
                # narrow peak can be attenuated by interpolation. Test agreement
                # against the closest measured bin and steer with the fractional value.
                nearest = frame.scores[first if fraction < 0.5 else second] / 127
                if ((value >= 0.08 and nearest >= baseline + contrast - 0.04) if gentle else relative >= 0.60):
                    supporting.append(pair)
            correlations.append(total / len(usable))
            support.append(supporting)
            # Trim only the strongest fifth; weak/disagreeing pairs still count.
            retained = sorted(evidence)[:len(usable) - len(usable) // 5]
            curve.append(sum(retained) / len(retained) if reject_reflections and not gentle else correlations[-1])
        peak = max(range(360), key=curve.__getitem__)
        if gentle:
            # Int8 telemetry often flattens the top of a low-frequency lobe.
            # Use the center of that connected plateau, not its first degree.
            edges = []
            for direction in (-1, 1):
                width = 0
                for step in range(1, 180):
                    if curve[peak] - curve[(peak + direction * step) % 360] > 1e-10:
                        break
                    width = step
                edges.append(width)
            peak = round(peak + (edges[1] - edges[0]) / 2) % 360
        other = max(curve[i] for i in range(360) if angle_distance(i, peak) >= (75 if gentle else 30))
        prominence = curve[peak] - other
        agreement = len(support[peak]) / len(usable)
        reason = ""
        if correlations[peak] < (0.10 if gentle else 0.12):
            reason = "Weak directional signal"
        elif reject_reflections and agreement < (0.50 if gentle else 0.65):
            reason = "Microphone pairs disagree"
        elif gentle and max(curve) - min(curve) < 0.006:
            reason = "Sound detected; direction unresolved"
        elif not gentle and prominence < (max(0.06, 0.12 * curve[peak]) if reject_reflections else 0.025):
            reason = "Competing or broad directions"
        return Bearing(peak, correlations[peak], prominence, not reason, tuple(curve), active,
                       agreement, len(support[peak]), len(usable), reason,
                       gentle and prominence < 0.025, tuple(map(len, support)))

    def demo(self, angle, sequence):
        scores = []
        for delay in self.delays(angle):
            scores.extend(round(110 * math.exp(-((lag - delay) ** 2) / 1.3))
                          for lag in range(-MAX_LAG, MAX_LAG + 1))
        energy = tuple(round(WINDOW * (45 + 10 * math.sin(sequence * 0.2 + i)) ** 2) for i in range(6))
        return Frame("D", sequence, sequence * WINDOW, 0, energy, tuple(scores))


class ReflectionTracker:
    """Conservative display gating, not acoustic echo cancellation.

    Temporal evidence is counted once per telemetry frame. Strong mode hides
    ambiguity and fading tails. Gentle mode can retain a currently supported
    local peak when a competing peak is only marginally stronger.
    A coherent persistent reflection can pass these tests just like a source.
    """

    def __init__(self, strength="strong"):
        self.strength = strength
        self.reset()

    def reset(self):
        self.last_key = None
        self.last_time = None
        self.last_result = None
        self.last_angle = None
        self.accepted_time = None
        self.pending_angle = None
        self.pending_count = 0
        self.previous_power = None
        self.peak_power = 0.0

    def update(self, frame, estimate, now=None):
        now = time.monotonic() if now is None else now
        key = (frame.source, frame.sequence, frame.samples)
        if key == self.last_key:
            return self.last_result
        if self.last_key is not None and (frame.source != self.last_key[0] or
                frame.sequence <= self.last_key[1] or now - self.last_time > 0.8):
            self.reset()
        elapsed = 0.0 if self.last_time is None else max(0.0, now - self.last_time)
        self.last_key, self.last_time = key, now
        power = statistics.median([frame.energy[i] / WINDOW for i in estimate.active_channels]) if estimate.active_channels else 0.0
        previous_power, self.previous_power = self.previous_power, power
        self.peak_power *= math.exp(-elapsed / 0.8)
        if self.accepted_time is not None and now - self.accepted_time > 0.65:
            self.last_angle = None
        gentle = self.strength == "gentle"
        if gentle and estimate.valid and self.last_angle is not None:
            nearby = max((i for i in range(360) if angle_distance(i, self.last_angle) <= 25),
                         key=lambda i: (estimate.curve[i], -angle_distance(i, self.last_angle)))
            best_score = max(estimate.curve)
            tolerance = max(0.012, 0.15 * (best_score - min(estimate.curve)))
            count = estimate.pair_counts[nearby]
            if (angle_distance(estimate.angle, self.last_angle) > 25 and
                    best_score - estimate.curve[nearby] <= tolerance and
                    estimate.curve[nearby] >= 0.10 and count / estimate.usable_pairs >= 0.50):
                # Keep the supported local peak, never just freeze an old
                # marker at an angle with no current evidence.
                estimate = replace(estimate, angle=nearby, correlation=estimate.curve[nearby],
                                   supporting_pairs=count, agreement=count / estimate.usable_pairs,
                                   uncertain=True)
        reason = estimate.reason
        if not estimate.valid:
            reason = reason or "No clear source"
        elif not gentle and self.peak_power and power < self.peak_power * 0.18:
            reason = "Fading sound suppressed"
        if reason:
            self.pending_angle, self.pending_count = None, 0
            self.last_result = replace(estimate, valid=False, reason=reason)
            return self.last_result

        self.peak_power = max(self.peak_power, power)
        close = self.last_angle is not None and angle_distance(estimate.angle, self.last_angle) <= 25
        # A clean new onset may be brief (a clap). Do not apply this exception
        # to a jump away from an established source.
        onset = (self.last_angle is None and previous_power is not None and
                 power > max(4.0, previous_power * 4) and estimate.agreement >= 0.85 and
                 estimate.correlation >= 0.30 and estimate.prominence >= 0.12)
        if not close and not onset:
            if self.pending_angle is not None and angle_distance(estimate.angle, self.pending_angle) <= 15:
                self.pending_count += 1
            else:
                self.pending_count = 1
            self.pending_angle = estimate.angle
            required = 2 if self.last_angle is None else (4 if gentle and angle_distance(estimate.angle, self.last_angle) >= 120 else 3)
            if self.pending_count < required:
                reason = "Checking new direction" if self.last_angle is not None else "Confirming source"
                self.last_result = replace(estimate, valid=False, reason=reason)
                return self.last_result

        angle = estimate.angle
        if close:
            delta = (angle - self.last_angle + 180) % 360 - 180
            angle = round(self.last_angle + 0.55 * delta) % 360
        self.last_angle, self.accepted_time = angle, now
        self.pending_angle, self.pending_count = None, 0
        self.last_result = replace(estimate, angle=angle)
        return self.last_result
