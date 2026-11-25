"""PySide6 dashboard for the six-channel acoustic radar."""
import argparse
import errno
import json
import math
import statistics
from contextlib import closing
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
import sys
import tempfile
import threading
import time
import wave

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QProgressBar, QPushButton, QDoubleSpinBox, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from . import ethernet
from .pcm import AudioCapture, RATE
from .takes import Take, TakeWriter, TAKES
from .replay import ReplayDialog, clock_text
from .localization import HEX_LOCATIONS, HEX_PORTS_MM, ReflectionTracker, Solver, bearing_vector, hex_ports_mm, positions, sound_speed
from .performance import PerformanceTrace
from .protocol import FPGA_INPUTS, FPGA_JE, HEX_INPUTS, HEX_PORT_ORDER, Frame, WINDOW
from .uart import BOOTLOADER, Console, PORT, PROMPT, STREAM

SETTINGS = Path(__file__).resolve().parents[1] / ".settings" / "gui.json"
THEMES = {
    "dark": ("#262626", "#303030", "#505050", "#eeeeee", "#b8b8b8", "#8dd8bd"),
    "light": ("#f1f1f1", "#ffffff", "#bcbcbc", "#262626", "#535353", "#217354"),
}


def array_level_db(frame):
    """Median active-channel power, on the same relative scale as the meters."""
    active = [power for power in frame.energy if power >= WINDOW * 4]
    power = statistics.median(active) if active else 0
    return 10 * math.log10(max(1, power) / (WINDOW * 512**2))


def channel_status(active_channels):
    quiet = [str(i + 1) for i in range(6) if i not in active_channels]
    status = f"{len(active_channels)}/6 mics active"
    if quiet:
        status += "  •  Quiet: " + ", ".join(quiet)
    return status


class BoardReader(QThread):
    received = Signal(object)
    report = Signal(str)

    retry_seconds = 1.5
    frame_timeout = 6

    def __init__(self, port):
        super().__init__()
        self.port = port
        self.stopped = threading.Event()

    def stop(self):
        self.stopped.set()

    def run(self):
        while not self.stopped.is_set():
            try:
                self.session()
            except (OSError, RuntimeError, ValueError) as error:
                if not self.stopped.is_set():
                    self.report.emit(self.retry_message(error))
            self.stopped.wait(self.retry_seconds)

    def retry_message(self, error):
        return f"{error} · retrying automatically"


LINK_NAMES = {"ethernet": "Ethernet", "wifi": "Wi-Fi", "uart": "USB UART"}


class NetworkReader(BoardReader):
    link_changed = Signal(str)

    def __init__(self, host, transport):
        super().__init__(host)
        self.transport = transport
        self.record_all = threading.Event()

    def session(self):
        self.report.emit(f"Connecting over {LINK_NAMES[self.transport]} · {self.port}")
        with closing(ethernet.live_frames(self.port, self.stopped.is_set, self.transport,
                                          self.link_changed.emit, self.record_all.is_set)) as frames:
            for frame in frames:
                self.received.emit(frame)


class UARTReader(BoardReader):
    def retry_message(self, error):
        if getattr(error, "errno", None) in (errno.ENOENT, errno.ENODEV, errno.ENXIO, errno.EIO):
            return "Waiting for Zybo USB · reconnecting automatically"
        return super().retry_message(error)

    def session(self):
        with Console(self.port) as console:
            while not self.stopped.is_set():
                self.report.emit("Waiting for Zybo Linux to start")
                if not console.wait_for_shell(self.stopped.is_set) or self.stopped.is_set():
                    return
                self.report.emit("Waiting for live FPGA data")
                console.send(STREAM + b" --stream\r")
                self.read_stream(console)

    def read_stream(self, console):
        started = heartbeat = time.monotonic()
        last_frame = None
        while not self.stopped.is_set():
            line = console.line()
            now = time.monotonic()
            if line.startswith(b"RADAR-ERROR"):
                raise RuntimeError(line.decode(errors="replace"))
            if BOOTLOADER.search(line) or line == b"RADAR-END":
                # Keep this descriptor and any following boot or login bytes.
                console.pending[:0] = line + b"\n"
                return
            if now - (last_frame or started) > self.frame_timeout:
                raise TimeoutError("FPGA stream timed out")
            if line.startswith(b"AR1 "):
                try:
                    frame = Frame.parse(line)
                except ValueError:
                    continue
                if frame.source == "L":
                    self.received.emit(frame)
                    last_frame = now
                    # Only a fresh live packet can trigger a heartbeat.
                    if now - heartbeat >= 2 and not self.stopped.is_set():
                        console.send(b"\r")
                        heartbeat = now

        if last_frame is not None and time.monotonic() - last_frame < 0.75:
            console.send(b"\x03")
            console.expect(PROMPT, 2)
            console.logout()


# Layout and temperature stay stable over many UART frames.
configured_solver = lru_cache(maxsize=8)(Solver)


class TakeAudioReader(QThread):
    def __init__(self, path, host, transport, channel_order):
        super().__init__()
        self.audio = AudioCapture(path, channel_order)
        self.host, self.transport = host, transport
        self.stopped = threading.Event()
        self.error = ""

    def run(self):
        try:
            self.audio.run(self.host, self.transport, self.stopped.is_set)
        except (OSError, ValueError, RuntimeError) as error:
            self.error = str(error)


class Polar(QWidget):
    def __init__(self, trace):
        super().__init__()
        self.setMinimumSize(400, 306)
        self.trace = trace
        self.playback_time = None
        self.mic_levels = [-60] * 6
        self.mic_positions = HEX_PORTS_MM
        self.palette_colors = THEMES["dark"]
        self.result = None
        self.raw_result = None
        self.filtered = True
        self.provisional = False
        self.ports_mm = None

    def paintEvent(self, event):
        del event
        _, panel, border, text, secondary, accent = map(QColor, self.palette_colors)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), panel)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = (min(self.width(), self.height()) - 92) / 2
        painter.setFont(QFont("DejaVu Sans", 9))
        for fraction in (0.25, 0.50, 0.75, 1.0):
            painter.setPen(QPen(border, 1))
            painter.drawEllipse(center, radius * fraction, radius * fraction)

        def point(angle, distance):
            dx, dy = bearing_vector(angle, self.ports_mm is not None)
            return QPointF(center.x() + distance * dx, center.y() - distance * dy)

        for angle in range(0, 360, 30):
            painter.setPen(QPen(border, 1))
            painter.drawLine(center, point(angle, radius))
            pos = point(angle, radius + 24)
            painter.setPen(text if angle % 90 == 0 else secondary)
            painter.drawText(QRectF(pos.x() - 42, pos.y() - 11, 84, 22), Qt.AlignmentFlag.AlignCenter,
                             "0° FRONT" if angle == 0 and self.ports_mm is None else f"{angle}°")

        for angle in range(0, 360, 5):
            painter.setPen(QPen(secondary if angle % 30 == 0 else border, 1))
            painter.drawLine(point(angle, radius - (7 if angle % 30 == 0 else 3)), point(angle, radius))

        def draw_response(result, color, filtered=False):
            curve = result.curve
            mean = sum(curve) / len(curve)
            scale = max(0.05, max(curve) - mean)
            visible = set(range(360))
            if filtered:
                # Keep only the connected lobe around the accepted maximum.
                # This is a display mask; it does not remove echoes from audio.
                peak = max((i for i in range(360) if abs((i - result.angle + 180) % 360 - 180) <= 25),
                           key=lambda i: (curve[i], -abs((i - result.angle + 180) % 360 - 180)))
                scale = max(0.005, curve[peak] - mean)
                threshold = mean + 0.55 * scale
                visible = {peak}
                for direction in (-1, 1):
                    for step in range(1, 90):
                        index = (peak + direction * step) % 360
                        if curve[index] < threshold:
                            break
                        visible.add(index)
            path = QPainterPath()
            for angle, score in enumerate(curve):
                strength = max(0, min(1, (score - mean) / scale))
                distance = radius * ((0.82 * strength if angle in visible else 0) if filtered else 0.27 + 0.55 * strength)
                pos = point(angle, distance)
                if angle == 0:
                    path.moveTo(pos)
                else:
                    path.lineTo(pos)
            path.closeSubpath()
            fill = QColor(color)
            fill.setAlpha(45 if result.valid else 20)
            painter.fillPath(path, fill)
            painter.setPen(QPen(color, 1.8 if result.valid else 1.0))
            painter.drawPath(path)

        if self.raw_result and self.raw_result.curve:
            draw_response(self.raw_result, secondary)
        if self.result and self.result.curve and (self.result.valid or not self.filtered):
            draw_response(self.result, accent, self.filtered)
            if self.result.valid:
                style = Qt.PenStyle.DashLine if self.provisional else Qt.PenStyle.SolidLine
                painter.setPen(QPen(accent, 2.5, style))
                target = point(self.result.angle, radius * 0.90)
                painter.drawLine(center, target)
                painter.setPen(QPen(accent, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush if self.provisional else accent)
                painter.drawEllipse(target, 5, 5)

        now = time.monotonic() if self.playback_time is None else self.playback_time
        # Recent accepted directions sit at a constant radius around the dial.
        for sample in reversed(self.trace.history):
            age = now - sample.time
            if age > 1.6 or sample.time < self.trace.trail_start:
                break
            if sample.angle is None:
                continue
            dot = QColor(accent)
            dot.setAlphaF(0.7 * max(0, 1 - age / 1.6))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot)
            size = 1.5 + 1.8 * sample.strength
            painter.drawEllipse(point(sample.angle, radius * 0.91), size, size)

        amber = QColor("#ffb967" if panel.lightness() < 128 else "#a04709")
        for mark in self.trace.arcs:
            fade = max(0, 1 - (now - mark.time) / self.trace.arc_lifetime)
            if not fade:
                continue
            path = QPainterPath()
            half_width = round(4 + 8 * mark.strength)
            for offset in range(-half_width, half_width + 1):
                pos = point(mark.angle + offset, radius * 0.97)
                if offset == -half_width:
                    path.moveTo(pos)
                else:
                    path.lineTo(pos)
            ink = QColor(amber)
            ink.setAlphaF(math.sqrt(fade) * (0.45 + 0.55 * mark.strength))
            glow = QColor(ink)
            glow.setAlphaF(ink.alphaF() * 0.22)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(glow, 10 + 4 * mark.strength, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
            pen = QPen(ink, 3 + 3 * mark.strength)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        mid_x, mid_y = (statistics.mean(axis) for axis in zip(*self.mic_positions))
        scale = radius * 0.25 / max(math.hypot(x-mid_x, y-mid_y) for x, y in self.mic_positions)
        mic_radius = max(8, min(radius * 0.043, 15))
        number_font = QFont("DejaVu Sans")
        number_font.setPixelSize(round(1.28 * mic_radius))
        painter.setFont(number_font)
        for i, (x, y) in enumerate(self.mic_positions):
            pos = QPointF(center.x() + (x-mid_x)*scale, center.y() - (y-mid_y)*scale)
            level = max(0, min(1, (self.mic_levels[i] + 60) / 60))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(panel)
            painter.drawEllipse(pos, mic_radius, mic_radius)
            fill = QColor(accent)
            fill.setAlphaF(level)
            painter.setBrush(fill)
            painter.setPen(QPen(secondary, 1))
            painter.drawEllipse(pos, mic_radius, mic_radius)
            painter.setPen(panel if level > 0.6 else text)
            painter.drawText(QRectF(pos.x()-mic_radius, pos.y()-mic_radius, 2*mic_radius, 2*mic_radius),
                             Qt.AlignmentFlag.AlignCenter, str(i+1))

        # A fixed-width instrument readout never displaces the compass or captions.
        degree_font = QFont("DejaVu Sans Mono")
        degree_font.setPixelSize(max(16, min(32, self.height() // 24)))
        painter.setFont(degree_font)
        bearing_text = "—"
        if self.result and self.result.valid:
            bearing_text = ("≈ " if self.provisional else "") + f"{self.result.angle:03d}°"
        painter.setPen(text)
        painter.drawText(self.rect().adjusted(12, 6, -12, -8),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, bearing_text)


class BearingHistory(QWidget):
    def __init__(self, trace):
        super().__init__()
        self.trace = trace
        self.palette_colors = THEMES["dark"]
        self.setFixedHeight(80)
        self.setAccessibleName("Bearing history over the last five seconds")
        self.setToolTip("Accepted bearings over the last five seconds. Gaps mark unresolved or gated sound.")

    def paintEvent(self, event):
        _, panel, border, text, secondary, accent = map(QColor, self.palette_colors)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), panel)
        p.setFont(QFont("DejaVu Sans", 9))
        p.setPen(text)
        p.drawText(QPointF(12, 16), "Bearing history")
        p.setPen(secondary)
        p.drawText(QRectF(100, 2, self.width()-112, 18), Qt.AlignmentFlag.AlignRight, "Last 5 s")
        left, right, top, bottom = 46, self.width()-12, 27, self.height()-10
        for degrees in (0, 180, 360):
            y = bottom - degrees / 360 * (bottom-top)
            p.setPen(secondary)
            p.drawText(QRectF(1, y-8, left-9, 16), Qt.AlignmentFlag.AlignRight, f"{degrees}°")
            p.setPen(QPen(border, 1))
            p.drawLine(QPointF(left, y), QPointF(right, y))
        for tick in range(6):
            x = left + tick * (right-left) / 5
            p.drawLine(QPointF(x, top), QPointF(x, bottom))
        now = time.monotonic()
        prior = None
        for mark in self.trace.history:
            age = now - mark.time
            if age > self.trace.duration or mark.angle is None:
                prior = None
                continue
            pos = QPointF(right-age/self.trace.duration*(right-left), bottom-mark.angle/360*(bottom-top))
            p.setPen(QPen(accent, 2, Qt.PenStyle.DotLine if mark.approximate else Qt.PenStyle.SolidLine))
            if prior:
                prev, prev_pos = prior
                if mark.time-prev.time < 0.4 and abs(mark.angle-prev.angle) <= 180:
                    p.drawLine(prev_pos, pos)
            p.drawPoint(pos)
            prior = mark, pos


class Dashboard(QMainWindow):
    def __init__(self, demo=False, port=None, host=None, wifi_host=None):
        super().__init__()
        self.setWindowTitle("Acoustic Radar | Zybo Z7-20")
        self.worker = None
        self.pc_link = ""
        self.frame = None
        self.trace = PerformanceTrace()
        self.filming = False
        self.take_writer = self.audio_reader = None
        self.take_error = ""
        self.last_take = None
        self.replay = None
        self.close_after_take = False
        self.demo_sequence = 0
        self.tracker = ReflectionTracker()
        self.last_frame_time = None
        self.settings = self.read_settings()
        recent = self.settings.get("last_take")
        if isinstance(recent, str) and Path(recent).is_file():
            self.last_take = Path(recent)
        self.theme = "light" if self.settings.get("theme") == "light" else "dark"
        self.persist = True
        self.resize(1050, 680)
        try:
            self.resize(int(self.settings.get("width", 1050)), int(self.settings.get("height", 680)))
        except (TypeError, ValueError, OverflowError):
            pass

        root = QWidget()
        self.setCentralWidget(root)
        columns = QHBoxLayout(root)
        columns.setContentsMargins(18, 18, 18, 18)
        columns.setSpacing(16)
        panel = self.sidebar = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(320)
        controls = QVBoxLayout(panel)
        controls.setContentsMargins(16, 16, 16, 16)
        controls.setSpacing(10)
        title = QLabel("Acoustic Radar")
        title.setObjectName("title")
        controls.addWidget(title)
        description = QLabel("Six INMP441 channels • Zybo Z7-20")
        description.setObjectName("muted")
        controls.addWidget(description)

        self.endpoints = {"uart": port or str(self.settings.get("port", PORT)),
                          "ethernet": host or str(self.settings.get("ethernet_host", ethernet.HOST)),
                          "wifi": wifi_host or str(self.settings.get("wifi_host", ethernet.WIFI_HOST))}
        self.transport = QComboBox()
        self.transport.setAccessibleName("Radar connection")
        self.transport.addItem("Ethernet · wired SSH", "ethernet")
        self.transport.addItem("USB UART · 115200 baud", "uart")
        self.transport.addItem("Wi-Fi · wireless SSH", "wifi")
        mode = self.settings.get("transport", "ethernet")
        if port is not None:
            mode = "uart"
        elif host is not None:
            mode = "ethernet"
        elif wifi_host is not None:
            mode = "wifi"
        self.transport.setCurrentIndex(max(0, self.transport.findData(mode)))
        controls.addWidget(self.transport)
        self.port = QLineEdit()
        self.transport.currentIndexChanged.connect(self.change_transport)
        self.port.textChanged.connect(self.update_endpoint)
        self.change_transport()
        controls.addWidget(self.port)
        session = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.demo_button = QPushButton("Demo")
        self.demo_button.setCheckable(True)
        session.addWidget(self.connect_button)
        session.addWidget(self.demo_button)
        controls.addLayout(session)
        self.connect_button.clicked.connect(self.connect_board)
        self.demo_button.toggled.connect(self.set_demo)

        self.layout_choice = QComboBox()
        self.layout_choice.addItem("Hexagon · 0° right, CCW", "hexagon")
        self.layout_choice.addItem("2 × 3 · 0° front, clockwise", "rectangle")
        self.layout_choice.setCurrentIndex(int(self.settings.get("array_layout") == "rectangle"))
        self.hex_measured = "hex_ports_mm" in self.settings and self.settings.get("hex_measured") is True
        try:
            saved_temp = float(self.settings.get("temperature_c", 20))
            sound_speed(saved_temp)
        except (ValueError, TypeError, OverflowError):
            saved_temp = 20.0
        try:
            self.ports_mm = hex_ports_mm(self.settings.get("hex_ports_mm", HEX_PORTS_MM))
            if "hex_ports_mm" in self.settings and "hex_port_order" not in self.settings:
                # Earlier releases stored offsets starting at the right, counterclockwise.
                self.ports_mm = tuple(self.ports_mm[i] for i in (2, 1, 0, 5, 4, 3))
            if "hex_ports_mm" in self.settings and self.settings.get("hex_port_order") != HEX_PORT_ORDER:
                # Rotate each measured opening into the opposite view and then renumber it.
                self.ports_mm = tuple((-self.ports_mm[i][0], -self.ports_mm[i][1]) for i in HEX_INPUTS)
            configured_solver(ports_mm=self.ports_mm, temperature_c=saved_temp)
        except ValueError:
            self.ports_mm = HEX_PORTS_MM
            self.hex_measured = False
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(-40, 60)
        self.temperature.setDecimals(1)
        self.temperature.setSuffix(" °C")
        self.temperature.setValue(saved_temp)
        self.column = self.distance(self.settings.get("column_mm", 50))
        self.row = self.distance(self.settings.get("row_mm", 100))
        self.geometry_form = QFormLayout()
        self.geometry_form.addRow("Array", self.layout_choice)
        self.geometry_form.addRow("Air temperature", self.temperature)
        self.geometry_form.addRow("Column spacing", self.column)
        self.geometry_form.addRow("Row spacing", self.row)
        controls.addLayout(self.geometry_form)
        self.port_editor = QPushButton("Acoustic-port coordinates…")
        self.port_editor.clicked.connect(self.edit_ports)
        controls.addWidget(self.port_editor)
        self.measured = QCheckBox("I measured this spacing")
        self.measured.setChecked(self.settings.get("measured") is True)
        self.measured.toggled.connect(self.on_measurement_changed)
        controls.addWidget(self.measured)
        self.column.valueChanged.connect(self.on_distance_changed)
        self.row.valueChanged.connect(self.on_distance_changed)

        self.swap_mics = QCheckBox("Swap MIC4 / MIC5 positions")
        self.swap_mics.setChecked(self.settings.get("swap_mic4_mic5") is True)
        self.swap_mics.setToolTip("Use when the lower-left microphone feeds JE9 (channel 5), and the lower-middle microphone feeds JE8 (channel 4). This changes geometry only; channel meters keep their JE channel numbers.")
        controls.addWidget(self.swap_mics)
        self.swap_mics.toggled.connect(self.on_mapping_changed)

        self.reject_reflections = QCheckBox("Reject reflections")
        self.reject_reflections.setChecked(self.settings.get("reject_reflections", True) is not False)
        self.reject_reflections.setToolTip("Stabilize direction and limit secondary lobes. Strong, steady reflections can still pass.")
        self.filter_strength = QComboBox()
        self.filter_strength.addItem("Gentle", "gentle")
        self.filter_strength.addItem("Strong", "strong")
        self.filter_strength.setCurrentIndex(1 if self.settings.get("filter_strength") == "strong" else 0)
        self.filter_strength.setToolTip("Gentle: show broad hum responses as approximate and resist opposite-side flips. Strong: reject ambiguous peaks and fading sound.")
        self.filter_strength.setEnabled(self.reject_reflections.isChecked())
        self.tracker = ReflectionTracker(self.filter_strength.currentData())
        self.raw_response = QCheckBox("Show raw response")
        self.raw_response.setChecked(self.settings.get("raw_response") is True)
        self.raw_response.setToolTip("Gray diagnostic pattern includes noise, sidelobes and possible reflections. It does not identify extra sources.")
        controls.addWidget(self.reject_reflections)
        filtering = QFormLayout()
        filtering.addRow("Filter strength", self.filter_strength)
        controls.addLayout(filtering)
        controls.addWidget(self.raw_response)
        self.reject_reflections.toggled.connect(self.on_filter_changed)
        self.filter_strength.currentIndexChanged.connect(self.on_filter_changed)
        self.raw_response.toggled.connect(self.on_view_changed)

        self.levels = []
        self.mic_labels = []
        levels = QFormLayout()
        for mic in range(1, 7):
            bar = QProgressBar()
            bar.setRange(-60, 0)
            bar.setValue(-60)
            bar.setTextVisible(False)
            bar.setFixedHeight(13)
            bar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            value = QLabel("quiet")
            value.setFixedWidth(58)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            line = QHBoxLayout()
            line.addWidget(bar, 1)
            line.addWidget(value)
            self.levels.append((bar, value))
            label = QLabel()
            self.mic_labels.append(label)
            levels.addRow(label, line)
        controls.addWidget(QLabel("Channel levels"))
        controls.addLayout(levels)
        controls.addStretch()
        self.diagnostics = QCheckBox("Show diagnostics")
        self.diagnostics.setChecked(self.settings.get("show_diagnostics") is True)
        controls.addWidget(self.diagnostics)
        self.theme_button = QPushButton()
        self.theme_button.clicked.connect(self.toggle_theme)
        view_controls = QHBoxLayout()
        view_controls.addWidget(self.theme_button)
        controls.addLayout(view_controls)
        columns.addWidget(panel)

        display = QVBoxLayout()
        self.status = QLabel("Disconnected")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        self.bearing = QLabel("No bearing")
        self.bearing.setObjectName("bearing")
        self.bearing.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.details = QLabel("Horizontal bearing from the front of the array")
        self.details.setWordWrap(True)
        self.details.setObjectName("muted")
        self.plot_status = QLabel("Connect to receive live directional data.")
        self.plot_status.setWordWrap(True)
        self.plot_status.setObjectName("muted")
        self.polar = Polar(self.trace)
        self.history_strip = BearingHistory(self.trace)
        self.film_status = QLabel()
        self.film_status.setObjectName("muted")
        self.film_status.setMaximumWidth(250)
        self.film_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.film_status.hide()
        self.film_button = QPushButton("Filming view  ·  F11")
        self.film_button.setToolTip("Toggle full-screen filming view (F11). Escape returns to the dashboard.")
        self.film_button.clicked.connect(self.toggle_filming)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_filming)
        self.leave_film = QShortcut(QKeySequence("Esc"), self, activated=self.toggle_filming)
        self.leave_film.setEnabled(False)
        header = QHBoxLayout()
        self.chart_title = QLabel("Sound direction")
        self.chart_title.setObjectName("title")
        self.chart_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self.chart_title, 1)
        header.addWidget(self.film_status)
        view_controls.addWidget(self.film_button)
        self.exit_film = QPushButton("Exit  ·  Esc")
        self.exit_film.clicked.connect(self.toggle_filming)
        self.exit_film.hide()
        header.addWidget(self.exit_film)
        display.addWidget(self.status)
        display.addLayout(header)
        display.addWidget(self.bearing)
        display.addWidget(self.plot_status)

        gate = QHBoxLayout()
        self.gate_enabled = QCheckBox("Level gate")
        self.gate_enabled.setChecked(self.settings.get("gate_enabled", True) is not False)
        self.gate_enabled.setToolTip("Hide the entire degree chart response below the threshold. Channel meters keep updating.")
        self.gate_slider = QSlider(Qt.Orientation.Horizontal)
        self.gate_slider.setRange(-60, 0)
        self.gate_slider.setPageStep(5)
        self.gate_slider.setAccessibleName("Minimum array level")
        try:
            threshold = float(self.settings.get("gate_db", -22))
            threshold = round(threshold) if math.isfinite(threshold) else -22
        except (TypeError, ValueError, OverflowError):
            threshold = -22
        self.gate_slider.setValue(threshold)
        self.gate_slider.setEnabled(self.gate_enabled.isChecked())
        self.gate_slider.setToolTip("Left: show quieter sounds. Right: require louder sounds. Relative dB, not calibrated sound-pressure level.")
        self.gate_value = QLabel()
        self.gate_value.setFixedWidth(54)
        self.array_level = QLabel("Array: -- dB")
        self.array_level.setFixedWidth(118)
        self.array_level.setToolTip("Median level of active microphones; quiet channels are excluded. Uses the channel meters' relative dB scale.")
        gate.addWidget(self.gate_enabled)
        gate.addWidget(self.gate_slider, 1)
        gate.addWidget(self.gate_value)
        gate.addWidget(self.array_level)
        self.gate_bar = QWidget()
        gate.setContentsMargins(0, 0, 0, 0)
        self.gate_bar.setLayout(gate)
        display.addWidget(self.gate_bar)
        self.gate_enabled.toggled.connect(self.on_gate_changed)
        self.gate_slider.valueChanged.connect(self.on_gate_changed)
        display.addWidget(self.polar, 1)
        display.addWidget(self.history_strip)
        display.addWidget(self.details)
        take_controls = QHBoxLayout()
        self.record_button = QPushButton("Record take")
        self.record_button.setToolTip("Record the six Zybo microphones and radar over Wi-Fi or Ethernet")
        self.record_button.clicked.connect(self.toggle_recording)
        self.replay_button = QPushButton("Replay last take" if self.last_take else "Replay take…")
        self.replay_button.clicked.connect(self.replay_recent)
        self.take_status = QLabel()
        self.take_status.setObjectName("muted")
        self.take_status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        for button in (self.record_button, self.replay_button):
            take_controls.addWidget(button)
        take_controls.addWidget(self.take_status, 1)
        display.addLayout(take_controls)
        columns.addLayout(display, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.animate_demo)
        self.stale_timer = QTimer(self)
        self.stale_timer.setInterval(250)
        self.stale_timer.timeout.connect(self.check_stale)
        self.stale_timer.timeout.connect(self.history_strip.update)
        self.stale_timer.timeout.connect(self.record_controls)
        self.stale_timer.start()
        self.layout_choice.currentIndexChanged.connect(self.change_layout)
        self.temperature.valueChanged.connect(self.on_mapping_changed)
        self.show_layout_controls()
        self.diagnostics.toggled.connect(self.toggle_diagnostics)
        self.show_diagnostics()
        self.apply_theme()
        self.refresh()
        self.record_controls()
        if demo:
            self.demo_button.setChecked(True)

    def toggle_filming(self):
        self.filming = not self.filming
        if self.filming:
            self.prior_window_state = self.windowState()
        else:
            # Restore the window before revealing the controls. At narrow widths
            # their wrapped captions otherwise raise the temporary minimum size.
            self.setWindowState(self.prior_window_state)
        self.bearing.setProperty("filming", self.filming)
        self.bearing.style().unpolish(self.bearing)
        self.bearing.style().polish(self.bearing)
        self.size_text_bands()
        self.sidebar.setVisible(not self.filming)
        self.gate_bar.setVisible(not self.filming)
        self.show_diagnostics()
        self.leave_film.setEnabled(self.filming)
        self.exit_film.setVisible(self.filming)
        if self.filming:
            self.showFullScreen()
        self.refresh()

    def show_diagnostics(self):
        visible = self.diagnostics.isChecked() and not self.filming
        for widget in (self.status, self.bearing, self.plot_status, self.history_strip, self.details, self.array_level):
            widget.setVisible(visible)
        self.film_status.show()

    def toggle_diagnostics(self):
        self.show_diagnostics()
        if self.persist:
            self.save()

    @staticmethod
    def distance(value):
        spin = QDoubleSpinBox()
        spin.setRange(1, 229)
        spin.setDecimals(1)
        spin.setSuffix(" mm")
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 50
        spin.setValue(number if math.isfinite(number) else 50)
        return spin

    @staticmethod
    def read_settings():
        try:
            value = json.loads(SETTINGS.read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def change_transport(self):
        mode = self.transport.currentData()
        self.port.setPlaceholderText(f"{LINK_NAMES[mode]} SSH host" if mode != "uart" else "Zybo UART device")
        self.port.setText(self.endpoints[mode])

    def update_endpoint(self, text):
        self.endpoints[self.transport.currentData()] = text.strip()
        self.port.setToolTip(text)

    def save(self):
        self.settings.update(array_layout=self.layout_choice.currentData(), hex_ports_mm=self.ports_mm,
                             hex_port_order=HEX_PORT_ORDER,
                             hex_measured=self.hex_measured, temperature_c=self.temperature.value())
        self.settings.update(theme=self.theme, transport=self.transport.currentData(),
                             port=self.endpoints["uart"], ethernet_host=self.endpoints["ethernet"], wifi_host=self.endpoints["wifi"],
                             column_mm=self.column.value(), row_mm=self.row.value(),
                             measured=self.measured.isChecked(),
                             width=self.normalGeometry().width() if self.isFullScreen() else self.width(),
                             height=self.normalGeometry().height() if self.isFullScreen() else self.height())
        self.settings.update(show_diagnostics=self.diagnostics.isChecked(), reject_reflections=self.reject_reflections.isChecked(),
                             raw_response=self.raw_response.isChecked(),
                             filter_strength=self.filter_strength.currentData(),
                             swap_mic4_mic5=self.swap_mics.isChecked(),
                             gate_enabled=self.gate_enabled.isChecked(), gate_db=self.gate_slider.value())
        path = None
        try:
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=SETTINGS.parent, delete=False) as file:
                path = Path(file.name)
                json.dump(self.settings, file, indent=2)
            path.replace(SETTINGS)
        except OSError:
            if path:
                path.unlink(missing_ok=True)

    def on_distance_changed(self):
        self.trace.reset()
        self.tracker.reset()
        self.measured.setChecked(False)
        self.refresh()

    def on_filter_changed(self):
        self.trace.reset()
        self.filter_strength.setEnabled(self.reject_reflections.isChecked())
        self.tracker = ReflectionTracker(self.filter_strength.currentData())
        self.on_view_changed()

    def on_mapping_changed(self):
        self.trace.reset()
        self.tracker.reset()
        self.on_view_changed()

    def on_gate_changed(self):
        self.trace.reset()
        self.gate_slider.setEnabled(self.gate_enabled.isChecked())
        self.tracker.reset()
        self.on_view_changed()

    def show_layout_controls(self):
        hexagon = self.layout_choice.currentData() == "hexagon"
        for control in (self.column, self.row):
            self.geometry_form.setRowVisible(control, not hexagon)
        self.swap_mics.setVisible(not hexagon)
        self.measured.setVisible(not hexagon)
        self.port_editor.setVisible(hexagon)
        self.polar.ports_mm = self.ports_mm if hexagon else None
        for mic, label in enumerate(self.mic_labels, 1):
            if hexagon:
                pin = FPGA_JE[HEX_INPUTS[mic - 1]]
                label.setText(f"M{mic} · {HEX_LOCATIONS[mic - 1]} · JE{pin}")
            else:
                label.setText(f"Mic {mic}")

    def change_layout(self):
        self.show_layout_controls()
        self.on_mapping_changed()

    def edit_ports(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Hexagon acoustic-port calibration")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Face the mic side with the wire harness at upper right. From the center, +X points right and +Y points up."))
        grid = QGridLayout()
        layout.addLayout(grid)
        for col, label in enumerate(("Mic", "X (mm)", "Y (mm)")):
            grid.addWidget(QLabel(label), 0, col)
        fields = []
        for mic, point in enumerate(self.ports_mm, 1):
            grid.addWidget(QLabel(f"M{mic} · {HEX_LOCATIONS[mic-1]}"), mic, 0)
            pair = []
            for col, value in enumerate(point, 1):
                spin = QDoubleSpinBox()
                spin.setDecimals(2)
                spin.setRange(-230, 230)
                spin.setValue(value)
                grid.addWidget(spin, mic, col)
                pair.append(spin)
            fields.append(pair)
        measured = QCheckBox("I measured these six acoustic openings")
        measured.setChecked(self.hex_measured)
        for pair in fields:
            for spin in pair:
                spin.valueChanged.connect(lambda _: measured.setChecked(False))
        layout.addWidget(measured)
        error = QLabel()
        layout.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        def accept():
            points = tuple((x.value(), y.value()) for x, y in fields)
            try:
                configured_solver(ports_mm=points, temperature_c=self.temperature.value())
            except ValueError as exc:
                error.setText(str(exc))
                return
            self.ports_mm = points
            self.hex_measured = measured.isChecked()
            dialog.accept()
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec():
            self.change_layout()

    def make_solver(self):
        if self.layout_choice.currentData() == "hexagon":
            return configured_solver(ports_mm=self.ports_mm, temperature_c=self.temperature.value())
        return configured_solver(self.column.value(), self.row.value(), self.swap_mics.isChecked(),
                                 temperature_c=self.temperature.value())

    def on_view_changed(self):
        self.refresh()
        if self.persist:
            self.save()

    def on_measurement_changed(self, measured):
        self.refresh()
        if measured and self.persist:
            self.save()

    def apply_theme(self):
        self.polar.palette_colors = THEMES.get(self.theme, THEMES["dark"])
        self.history_strip.palette_colors = self.polar.palette_colors
        self.history_strip.update()
        background, panel, border, text, secondary, accent = self.polar.palette_colors
        self.theme_button.setText("Light theme" if self.theme == "dark" else "Dark theme")
        self.setStyleSheet(f"""
            QWidget {{background: {background}; color: {text}; font-size: 13px}}
            QFrame#panel {{background: {panel}; border: 1px solid {border}; border-radius: 8px}}
            QFrame#panel QLabel, QFrame#panel QCheckBox {{background: transparent}}
            QLabel#title {{font-size: 24px; font-weight: bold}}
            QLabel#muted {{color: {secondary}}}
            QLabel#bearing {{font-size: 31px; font-weight: bold}}
            QLabel#bearing[filming="true"] {{font-size: 48px}}
            QLineEdit, QDoubleSpinBox, QComboBox, QPushButton, QProgressBar {{
                background: {panel}; border: 1px solid {border}; border-radius: 5px; padding: 4px
            }}
            QPushButton:hover, QPushButton:checked {{border-color: {accent}; color: {accent}}}
            QCheckBox::indicator {{background: {background}; border: 1px solid {border}; width: 14px; height: 14px; border-radius: 3px}}
            QCheckBox::indicator:checked {{background: {accent}; border-color: {accent}}}
            QProgressBar {{padding: 0px}}
            QProgressBar::chunk {{background: {accent}; border-radius: 4px}}
            QSlider::groove:horizontal {{height: 5px; background: {border}; border-radius: 2px}}
            QSlider::sub-page:horizontal {{background: {accent}; border-radius: 2px}}
            QSlider::handle:horizontal {{background: {accent}; border: 1px solid {border}; width: 13px; margin: -5px 0; border-radius: 6px}}
            QSlider::sub-page:horizontal:disabled, QSlider::handle:horizontal:disabled {{background: {secondary}}}
        """)
        self.size_text_bands()
        self.polar.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.size_text_bands()

    def size_text_bands(self):
        # Reserve enough rows for wrapped telemetry at this window width.
        # Only a resize or a theme change may change the chart bounds.
        layout = self.centralWidget().layout()
        margins = layout.contentsMargins()
        width = self.width() - margins.left() - margins.right()
        if not self.filming:
            width -= layout.spacing() + self.sidebar.width()
        narrow = width < self.plot_status.fontMetrics().horizontalAdvance(
            "Broad / competing response · approximate direction · Gray: raw response")
        for label, lines in ((self.status, 1), (self.bearing, 1),
                             (self.plot_status, 3 if narrow else 2), (self.details, 3 if narrow else 2)):
            label.ensurePolished()
            metrics = label.fontMetrics()
            sample = "≈ 359°" if label is self.bearing else "Ag"
            label.setFixedHeight(metrics.size(Qt.TextFlag.TextSingleLine, sample).height()
                                 + (lines - 1) * metrics.lineSpacing())
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.apply_theme()
        self.save()

    def connect_board(self):
        if self.worker:
            self.connect_button.setEnabled(False)
            self.worker.stop()
            self.board_status("Disconnecting")
            return
        self.demo_button.setChecked(False)
        mode = self.transport.currentData()
        endpoint = self.port.text().strip()
        self.worker = UARTReader(endpoint) if mode == "uart" else NetworkReader(endpoint, mode)
        if self.persist:
            self.save()
        self.transport.setEnabled(False)
        self.pc_link = ""
        if isinstance(self.worker, NetworkReader):
            self.worker.link_changed.connect(self.set_pc_link)
        self.worker.received.connect(self.board_frame)
        self.worker.report.connect(self.worker_status)
        self.worker.finished.connect(self.board_closed)
        self.port.setReadOnly(True)
        self.connect_button.setText("Disconnect")
        self.connect_button.setToolTip("Pause automatic connection")
        self.board_status(f"Opening {LINK_NAMES[mode]}")
        self.worker.start()

    def board_status(self, message):
        if self.audio_reader and self.frame is not None:
            self.stop_take("Radar connection changed during the take")
        if self.status.text() == message and self.frame is None:
            return
        self.status.setText(message)
        self.status.setToolTip(message)
        self.frame = None
        self.last_frame_time = None
        self.tracker.reset()
        self.refresh()

    def set_pc_link(self, link):
        if self.sender() is self.worker:
            self.pc_link = link

    def worker_status(self, message):
        if self.worker and not self.worker.stopped.is_set():
            self.board_status(message)

    def board_frame(self, frame):
        if self.worker and not self.worker.stopped.is_set():
            self.accept_frame(frame)

    def board_closed(self):
        self.worker.deleteLater()
        self.worker = None
        self.port.setReadOnly(False)
        self.transport.setEnabled(True)
        self.connect_button.setText("Connect")
        self.connect_button.setToolTip("Connect automatically whenever the Zybo is available")
        self.connect_button.setEnabled(True)
        if not self.demo_button.isChecked():
            self.board_status("Disconnected")

    def set_demo(self, enabled):
        self.trace.reset()
        self.tracker.reset()
        if enabled:
            if self.worker:
                self.worker.stop()
                self.connect_button.setEnabled(False)
            self.last_frame_time = None
            self.status.setText("Demo · simulated microphone data")
            self.timer.start()
            self.animate_demo()
        else:
            self.timer.stop()
            self.frame = None
            self.status.setText("Disconnected")
            self.refresh()

    def animate_demo(self):
        self.demo_sequence += 1
        try:
            solver = self.make_solver()
        except ValueError as error:
            self.details.setText(str(error))
            return
        frame = solver.demo(self.demo_sequence * 3 % 360, self.demo_sequence)
        envelope = (12, 7, 4, 2, 1, 0.5, 0.1, 0.02)[(self.demo_sequence - 1) % 8]
        self.frame = replace(frame, energy=tuple(round(e * envelope) for e in frame.energy))
        self.refresh(solver)
        self.record_window()


    def accept_frame(self, frame):
        self.frame = frame
        self.last_frame_time = time.monotonic()
        link = LINK_NAMES[self.transport.currentData()]
        self.status.setText(f"Connected · FPGA live · window {frame.sequence} · {link}")
        self.status.setToolTip(link)
        self.refresh()
        self.record_window()

    def record_window(self):
        result = self.polar.result
        angle = result.angle if result and result.valid else None
        self.trace.observe(self.frame, time.monotonic(), self.frame_level, angle,
                           self.polar.provisional, self.gated)
        self.history_strip.update()

        if self.take_writer and self.frame.source == "L" and not self.take_error:
            try:
                self.take_writer.capture(self.polar, self.bearing.text(), self.frame_for_layout())
            except (OSError, ValueError) as error:
                self.stop_take(str(error))

    def take_message(self, text):
        self.take_status.setText(text)
        self.take_status.setToolTip(text)

    def record_controls(self):
        if self.audio_reader:
            stopping = self.audio_reader.stopped.is_set()
            self.record_button.setEnabled(not stopping)
            if self.audio_reader.audio.frames and not stopping:
                length = self.audio_reader.audio.frames / RATE
                self.take_message(f"Recording  ·  {clock_text(length)}  ·  M1–M6")
        else:
            live = self.frame is not None and self.frame.source == "L" and self.worker is not None
            self.record_button.setEnabled(live and self.transport.currentData() in ethernet.INTERFACES)

    def stop_take(self, error=""):
        if self.audio_reader:
            self.take_error = self.take_error or error
            self.audio_reader.stopped.set()
            self.record_button.setEnabled(False)
            self.take_message("Finishing take…")

    def toggle_recording(self):
        if self.audio_reader:
            self.stop_take()
            return
        if not self.worker or not self.frame or self.frame.source != "L" or not isinstance(self.worker, NetworkReader):
            self.take_message("Connect to the live Zybo over Wi-Fi or Ethernet to record.")
            return
        try:
            self.take_writer = TakeWriter(TAKES)
        except OSError as error:
            self.take_message(str(error))
            return
        self.take_error = ""
        channel_order = HEX_INPUTS if self.layout_choice.currentData() == "hexagon" else FPGA_INPUTS
        self.audio_reader = TakeAudioReader(self.take_writer.path, self.worker.port, self.worker.transport, channel_order)
        self.layout_choice.setEnabled(False)
        self.audio_reader.finished.connect(self.take_finished)
        self.take_message("Waiting for Zybo microphone audio…")
        self.record_button.setText("Stop recording")
        self.demo_button.setEnabled(False)
        self.worker.record_all.set()
        self.audio_reader.start()

    def take_finished(self):
        reader = self.audio_reader
        if isinstance(self.worker, NetworkReader):
            self.worker.record_all.clear()
        error = self.take_error or reader.error
        if not reader.audio.frames and not error:
            error = "Stopped before the first audio packet"
        path = self.take_writer.path
        finalized = False
        try:
            self.take_writer.finish(reader.audio, error)
            finalized = True
        except OSError as problem:
            error = str(problem)
        if finalized and reader.audio.frames:
            self.last_take = path / "take.jsonl"
            self.replay_button.setText("Replay last take")
            self.settings["last_take"] = str(self.last_take)
            if self.persist:
                self.save()
        self.take_message(f"Take interrupted · {error}" if error else f"Saved {clock_text(reader.audio.frames/RATE)} · {path.name}")
        self.take_writer = self.audio_reader = None
        reader.deleteLater()
        self.demo_button.setEnabled(True)
        self.layout_choice.setEnabled(True)
        self.record_button.setText("Record take")
        self.record_controls()
        if self.close_after_take:
            self.close()

    def replay_recent(self):
        if self.last_take and self.last_take.is_file():
            self.open_take(self.last_take)
        else:
            self.choose_take()

    def choose_take(self):
        path, _ = QFileDialog.getOpenFileName(self, "Replay a Zybo recording",
                                               str(self.last_take or TAKES), "Radar take (take.jsonl)")
        if path:
            self.open_take(path)

    def open_take(self, path):
        try:
            take = Take.load(path)
        except (OSError, EOFError, ValueError, TypeError, KeyError, wave.Error) as error:
            self.take_message(f"Unable to open take · {error}")
            return
        if self.replay is not None:
            self.replay.close()
            if self.replay.isVisible():
                return
            self.replay.deleteLater()
        self.replay = ReplayDialog(take, Polar, self.theme, self.polar.palette_colors, self)
        self.replay.show()

    def check_stale(self):
        if self.worker and self.frame and self.last_frame_time is not None and time.monotonic() - self.last_frame_time > 1.0:
            self.frame = None
            self.tracker.reset()
            self.refresh()
            self.status.setText("Waiting for fresh FPGA data")
            self.film_status.setText("Waiting for Zybo")
            self.plot_status.setText("Stale bearing cleared")

    def frame_for_layout(self):
        if self.frame is not None and self.frame.source == "L" and self.layout_choice.currentData() == "hexagon":
            return self.frame.in_hex_order()
        return self.frame

    def refresh(self, solver=None):
        frame = self.frame_for_layout()
        self.polar.result = None
        self.polar.raw_result = None
        self.polar.filtered = self.reject_reflections.isChecked()
        self.polar.provisional = False
        self.bearing.setText("No bearing")
        self.plot_status.setText("Waiting for live directional data." if self.worker
                                 else "Connect to receive live directional data.")
        self.details.setText("0° toward M3 (right) · angles increase counterclockwise" if self.polar.ports_mm
                             else "Horizontal bearing from the front of the array")
        self.gate_value.setText(f"{self.gate_slider.value()} dB")
        level = array_level_db(frame) if frame else None
        self.frame_level = level
        self.gated = level is not None and self.gate_enabled.isChecked() and level < self.gate_slider.value()
        if frame is None:
            self.trace.reset()
            self.history_strip.update()
            self.film_status.setText("Waiting for Zybo" if self.worker else "Disconnected")
            self.film_status.setToolTip(self.status.text())
        else:
            source = "Demo" if frame.source == "D" else f"Live · {LINK_NAMES[self.transport.currentData()]}"
            if frame.source == "L" and self.pc_link:
                source = f"{self.pc_link} → Zybo {LINK_NAMES[self.transport.currentData()]}"
            self.film_status.setText(source)
            self.film_status.setToolTip(self.status.text())
        if self.polar.ports_mm is not None:
            self.polar.mic_positions = self.polar.ports_mm
        else:
            coords = list(positions(self.column.value(), self.row.value()))
            if self.swap_mics.isChecked():
                coords[3], coords[4] = coords[4], coords[3]
            self.polar.mic_positions = coords
        self.array_level.setText(f"Array: {level:.1f} dB" if level is not None else "Array: -- dB")
        for mic, (bar, value) in enumerate(self.levels):
            energy = frame.energy[mic] if frame else 0
            db = round(10 * math.log10(max(1, energy) / (WINDOW * 512**2)))
            self.polar.mic_levels[mic] = db
            bar.setValue(max(-60, db))
            value.setText("quiet" if db < -60 else f"{db} dB")
        if self.gated:
            self.trace.quiet()
            # Gate both the accepted response and optional raw overlay. Reset
            # temporal evidence so a hidden frame cannot confirm a future track.
            self.tracker.reset()
            self.bearing.setText("Below level gate")
            self.plot_status.setText(f"Array {level:.1f} dB < gate {self.gate_slider.value()} dB · chart hidden")
            active = tuple(i for i, power in enumerate(frame.energy) if power >= WINDOW * 4)
            self.details.setText(channel_status(active))
            if len(active) < 3:
                self.bearing.setText("Waiting for sound" if self.filming else "Waiting for mic activity")
                self.plot_status.setText("Direction needs three active mics that form a triangle. The level gate is also closed.")
            self.polar.update()
            return
        try:
            if solver is None:
                solver = self.make_solver()
            if frame:
                self.update_radar(solver, frame)
        except ValueError as error:
            self.plot_status.setText(str(error))
        self.polar.update()

    def update_radar(self, solver, frame):
        filtering = self.reject_reflections.isChecked()
        strength = self.filter_strength.currentData()
        estimate = solver.estimate(frame, reject_reflections=filtering, strength=strength)
        if filtering:
            estimate = self.tracker.update(frame, estimate)
        if self.raw_response.isChecked():
            self.polar.raw_result = solver.estimate(frame, reject_reflections=False)
        measured = self.hex_measured if solver.xy_angles else self.measured.isChecked()
        unmeasured = frame.source == "L" and not measured
        provisional = unmeasured or estimate.uncertain
        self.polar.result = estimate
        self.polar.provisional = provisional
        if estimate.valid:
            prefix = "≈ " if provisional else ""
            self.bearing.setText(f"{prefix}{estimate.angle:03d}°")
        elif estimate.curve:
            self.bearing.setText("No clear source")
        else:
            self.bearing.setText("Waiting for sound" if self.filming else "Waiting for mic activity")

        geometry = "Estimated port positions" if unmeasured else "Directional correlation"
        pattern = "Live" if frame.source == "L" else "Demo"
        if estimate.curve:
            mode = f"{strength.title()} filtering" if filtering else "Unfiltered response"
            state = ("Broad / competing response · approximate direction" if estimate.uncertain else "Source tracked") if estimate.valid else estimate.reason
            raw = " · Gray: raw response" if self.raw_response.isChecked() else ""
            self.plot_status.setText(f"{pattern} · {geometry} · {mode}\n{state}{raw}")
        else:
            self.plot_status.setText("Direction needs three active mics that form a triangle.")

        stats = [channel_status(estimate.active_channels)]
        if not solver.xy_angles and self.swap_mics.isChecked():
            stats.append("MIC4/5 positions swapped")
        stats.extend((f"Peak correlation {estimate.correlation:.2f}",
                      f"Pair agreement {estimate.supporting_pairs}/{estimate.usable_pairs}",
                      f"Dropped frames {frame.dropped}"))
        self.details.setText("  •  ".join(stats))

    def closeEvent(self, event):
        if self.replay and self.replay.isVisible() and not self.replay.close():
            event.ignore()
            return
        if self.audio_reader:
            self.close_after_take = True
            self.stop_take()
            event.ignore()
            return
        if self.persist:
            self.save()
        if self.worker:
            self.worker.stop()
            if not self.worker.wait(15000):
                event.ignore()
                return
        event.accept()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Show simulated signals without a board")
    link = parser.add_mutually_exclusive_group()
    link.add_argument("--host", help="Connect over Ethernet using this wired SSH host")
    link.add_argument("--wifi", nargs="?", const="", metavar="HOST", help="Connect over Wi-Fi using the saved or specified SSH host")
    link.add_argument("--port", help="Connect over USB UART using auto or an explicit serial device")
    parser.add_argument("--connect", action="store_true", help="Start with automatic Zybo connection (default)")
    parser.add_argument("--preview", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--theme", choices=tuple(THEMES), help="Override the initial color theme")
    args = parser.parse_args()
    if args.demo and args.connect:
        parser.error("choose --demo or --connect")
    app = QApplication([])
    window = Dashboard(args.demo, args.port, args.host, args.wifi)
    window.persist = args.preview is None
    if args.theme:
        window.theme = args.theme
        window.apply_theme()
    window.show()
    if args.connect or (not args.demo and args.preview is None):
        QTimer.singleShot(0, window.connect_board)
    if args.preview:
        def finish():
            if not window.grab().save(str(args.preview)):
                app.exit(1)
            else:
                app.quit()
        QTimer.singleShot(1800 if args.connect else 750, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
