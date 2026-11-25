"""Render the stored compass and the selected synchronized microphone audio for video editors."""
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from .gui import Polar, THEMES
from .performance import PerformanceTrace
from .pcm import CHANNELS
from .takes import Take


def render(take, target, theme, size=1080, fps=30, audio_source="m1"):
    if target.suffix.lower() != ".mp4":
        raise ValueError("Choose an MP4 filename")
    audio = take.audio_path(audio_source)
    mix = []
    if audio_source == "all":
        mix = ["-af", "pan=mono|c0<" + "+".join(f"c{i}" for i in range(CHANNELS))]
    timing = []
    if take.clock:
        timing = ["-metadata", "creation_time=" + take.clock.metadata()["first_sample_utc"],
                  "-timecode", take.clock.timecode(fps)]
    polar = Polar(PerformanceTrace())
    polar.palette_colors = THEMES[theme]
    polar.ports_mm = polar.mic_positions
    band = size // 12
    polar.resize(size, size-band)
    image = QImage(size, size, QImage.Format.Format_RGB888)
    total = max(1, math.ceil(take.duration * fps))
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        staged = Path(tmp) / "radar.mp4"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{size}x{size}", "-r", str(fps), "-i", "pipe:0", "-i", str(audio),
               "-map", "0:v:0", "-map", "1:a:0", *mix, *timing, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-threads", "4", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
               "-t", f"{take.duration:.8f}", str(staged)]
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as process:
            try:
                for i in range(total):
                    pos = i / fps
                    frame = take.frame_at(pos)
                    take.apply(polar, frame, pos)
                    image.fill(QColor(polar.palette_colors[1]))
                    painter = QPainter(image)
                    polar.render(painter, QPoint(0, band))
                    font = QFont("DejaVu Sans")
                    font.setPixelSize(band // 2)
                    painter.setFont(font)
                    painter.setPen(QColor(polar.palette_colors[3]))
                    painter.drawText(0, 0, size, band, Qt.AlignmentFlag.AlignCenter,
                                     "Sound direction")
                    painter.end()
                    process.stdin.write(image.constBits())
                    if i % (5 * fps) == 0:
                        print(f"Rendering {100*i//total}%", flush=True)
            finally:
                process.stdin.close()
            if process.wait():
                raise RuntimeError("FFmpeg could not encode the MP4")
        os.replace(staged, target)


if __name__ == "__main__":
    app = QApplication([])
    try:
        render(Take.load(sys.argv[1]), Path(sys.argv[2]), sys.argv[3],
               audio_source=sys.argv[4] if len(sys.argv) > 4 else "m1")
    except (OSError, ValueError, RuntimeError) as error:
        sys.exit(str(error))
