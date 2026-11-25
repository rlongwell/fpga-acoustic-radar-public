"""Replay recorded measurements on the compass and export an editing clip."""
import os
from pathlib import Path
import re
import sys
import wave

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout

from .performance import PerformanceTrace
from .pcm import CHANNELS
from .takes import Take


def clock_text(seconds):
    tenths = int(seconds * 10)
    return f"{tenths // 600}:{tenths // 10 % 60:02d}.{tenths % 10}"


def all_mics_sink(output="autoaudiosink"):
    # Explicit channel indices include every mic even on stereo/mono speakers.
    row = ",".join([f"(float){1 / CHANNELS:.9f}"] * CHANNELS)
    return (f'capsfilter caps=audio/x-raw,format=F32LE,channels={CHANNELS} ! '
            f'audioconvert mix-matrix="<<{row}>>" ! audio/x-raw,format=F32LE,channels=1 ! '
            f'audioconvert ! audioresample ! {output}')


class ReplayDialog(QDialog):
    def __init__(self, take, polar_class, theme, colors, parent):
        super().__init__(parent)
        self.setWindowTitle("Acoustic Radar | Replay take")
        self.resize(800, 760)
        self.take, self.theme = take, theme
        self.position = 0.
        self.player = None
        self.encoder = None
        layout = QVBoxLayout(self)
        self.bearing = QLabel("Sound direction")
        self.bearing.setObjectName("bearing")
        layout.addWidget(self.bearing)
        self.polar = polar_class(PerformanceTrace())
        self.polar.palette_colors = colors
        self.polar.ports_mm = self.polar.mic_positions
        layout.addWidget(self.polar, 1)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setAccessibleName("Take position")
        self.slider.setRange(0, round(take.duration * 1000))
        self.slider.sliderPressed.connect(self.start_seek)
        self.slider.sliderReleased.connect(self.finish_seek)
        self.slider.valueChanged.connect(self.slider_changed)
        layout.addWidget(self.slider)
        controls = QHBoxLayout()
        self.play = QPushButton("Play")
        self.play.clicked.connect(self.toggle)
        self.elapsed = QLabel()
        self.elapsed.setMinimumWidth(120)
        self.export = QPushButton("Export MP4…")
        self.export.clicked.connect(self.choose_export)
        other = QPushButton("Open another take…")
        other.clicked.connect(parent.choose_take)
        for widget in (self.play, self.elapsed, other, self.export):
            controls.addWidget(widget)
        layout.addLayout(controls)
        audio_row = QHBoxLayout()
        label = QLabel("Audio")
        self.audio_source = QComboBox()
        self.audio_source.setAccessibleName("Replay audio source")
        label.setBuddy(self.audio_source)
        self.audio_source.addItem("M1 only", "m1")
        self.audio_source.addItem("All six mics", "all")
        self.audio_source.setToolTip("Listen and export with M1 or an equal mono mix of M1–M6")
        try:
            take.audio_path("all")
        except (OSError, EOFError, ValueError, wave.Error) as error:
            option = self.audio_source.model().item(1)
            option.setEnabled(False)
            self.audio_source.setToolTip(f"All six mics unavailable · {error}")
        else:
            self.audio_source.setCurrentIndex(int(parent.settings.get("replay_audio") == "all"))
        self.audio_source.currentIndexChanged.connect(self.change_audio)
        audio_row.addWidget(label)
        audio_row.addWidget(self.audio_source)
        audio_row.addStretch()
        if take.clock:
            stamp = take.clock.start_local
            start_label = QLabel(f"Start {stamp:%Y-%m-%d %H:%M:%S}  ·  TC {take.clock.timecode(30)}")
            start_label.setToolTip(f"PC local time {stamp.isoformat(timespec='milliseconds')} · 30 fps")
            start_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            audio_row.addWidget(start_label)
        layout.addLayout(audio_row)
        self.note = QLabel(take.error or take.path.parent.name)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.seek_resume = False
        self.show_position(0)

    def show_position(self, position):
        self.position = min(self.take.duration, max(0., position))
        frame = self.take.frame_at(self.position)
        Take.apply(self.polar, frame, self.position)
        self.elapsed.setText(f"{clock_text(self.position)} / {clock_text(self.take.duration)}")
        self.slider.blockSignals(True)
        self.slider.setValue(round(self.position * 1000))
        self.slider.blockSignals(False)

    def start_seek(self):
        self.seek_resume = self.player is not None
        self.pause()

    def finish_seek(self):
        if self.seek_resume:
            self.start_audio()
        self.seek_resume = False

    def slider_changed(self, value):
        resume = self.player is not None
        if resume:
            self.pause()
        self.show_position(value / 1000)
        if resume:
            self.start_audio()

    def toggle(self):
        if self.player is not None:
            self.pause()
        else:
            if self.position >= self.take.duration:
                self.show_position(0)
            self.start_audio()

    def change_audio(self):
        parent = self.parent()
        parent.settings["replay_audio"] = self.audio_source.currentData()
        if parent.persist:
            parent.save()
        if self.player is not None:
            self.pause()
            self.start_audio()

    def start_audio(self):
        source = self.audio_source.currentData()
        try:
            audio = self.take.audio_path(source)
        except (OSError, EOFError, ValueError, wave.Error) as error:
            self.note.setText(f"Unable to play audio · {error}")
            return
        player = self.player = QProcess(self)
        player.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.pending = b""
        self.diagnostic = ""
        player.readyReadStandardOutput.connect(lambda: self.audio_output(player))
        player.finished.connect(lambda code, _: self.audio_finished(player, code))
        player.errorOccurred.connect(lambda _: self.audio_error(player))
        self.play.setText("Pause")
        args = ["--no-interactive", "-a", "-s", f"{self.position:.5f}"]
        if source == "all":
            args.extend(["--audiosink", all_mics_sink()])
        player.start("gst-play-1.0", [*args, str(audio)])

    def audio_output(self, player):
        if self.player is not player:
            return
        data = self.pending + bytes(player.readAllStandardOutput())
        lines = re.split(rb"[\r\n]", data)
        self.pending = lines.pop()[-1024:]
        # Follow the actual audio player's clock for local preview.
        for line in lines:
            match = re.match(rb"(\d+):(\d+):([\d.]+) / ", line.strip())
            if match:
                h, m, s = match.groups()
                self.show_position(int(h)*3600 + int(m)*60 + float(s))
            elif b"error" in line.lower():
                self.diagnostic = line.decode(errors="replace")

    def audio_finished(self, player, code):
        if self.player is not player:
            return
        self.audio_output(player)
        self.player = None
        self.play.setText("Play")
        if code or self.diagnostic:
            self.note.setText(self.diagnostic or "Audio playback failed. Check the PC audio output.")
        else:
            self.show_position(self.take.duration)
        player.deleteLater()

    def audio_error(self, player):
        if self.player is player and player.error() == QProcess.ProcessError.FailedToStart:
            self.note.setText("Audio playback needs gst-play-1.0 from gstreamer1.0-plugins-base-apps.")
            self.player = None
            self.play.setText("Play")
            player.deleteLater()

    def pause(self):
        player, self.player = self.player, None
        if player is not None:
            player.kill()
            player.waitForFinished(1500)
            player.deleteLater()
        self.play.setText("Play")

    def choose_export(self):
        dialog = QFileDialog(self, "Export radar and guitar", str(self.take.path.parent), "MP4 video (*.mp4)")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDefaultSuffix("mp4")
        dialog.selectFile("radar.mp4")
        if dialog.exec():
            target = Path(dialog.selectedFiles()[0])
            if target.suffix.lower() == ".mp4":
                self.start_export(target)
            else:
                self.note.setText("Choose a filename ending in .mp4")

    def start_export(self, path):
        self.export.setEnabled(False)
        job = self.encoder = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("QT_QPA_PLATFORM", "offscreen")
        job.setProcessEnvironment(env)
        job.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        job.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.export_log = ""
        def read():
            log = bytes(job.readAllStandardOutput()).decode(errors="replace").strip()
            if log:
                self.export_log = log[-500:]
                self.note.setText(self.export_log)
        def done(code, _):
            read()
            self.note.setText(f"Saved {path}" if code == 0 else f"Export failed · {self.export_log}")
            self.encoder = None
            self.export.setEnabled(True)
            job.deleteLater()
        job.readyReadStandardOutput.connect(read)
        job.finished.connect(done)
        self.note.setText("Rendering the radar and guitar soundtrack…")
        job.start(sys.executable, ["-m", "radar.export", str(self.take.path), os.fspath(path), self.theme,
                                   self.audio_source.currentData()])

    def reject(self):
        if self.encoder is not None:
            self.note.setText("Finishing MP4 export…")
            return
        self.pause()
        super().reject()
