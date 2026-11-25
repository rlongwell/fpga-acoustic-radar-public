from dataclasses import replace
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import shutil
import struct
import subprocess
import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from radar.pcm import AudioCapture, BLOCK, HEADER, RATE
from radar.protocol import FPGA_INPUTS, HEX_INPUTS
from radar.takes import Take, TakeWriter
from radar.sync import TakeClock


class AudioFixture(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def capture(self, path, indices, channel_order=FPGA_INPUTS):
        # Different signed 24-bit words on all six channels, including low bits.
        pattern = bytes.fromhex("0197ff553302870cff0a00b6e001739f0180")
        wire = b"".join(HEADER.pack(b"PCM6", i, BLOCK, RATE) + pattern * BLOCK for i in indices)
        blob = self.root / "wire"
        blob.write_bytes(wire)
        peer = [sys.executable, "-c", "import sys;print('PCM-READY',flush=True);sys.stdin.buffer.readline();data=open(sys.argv[1],'rb').read();"
                "sys.stdout.buffer.write(data);sys.stdout.flush();sys.stdin.buffer.read()", str(blob)]
        pcm = AudioCapture(path, channel_order)
        with patch("radar.pcm.ssh_command", return_value=peer):
            pcm.run("board", "wifi", lambda: pcm.frames == len(indices) * BLOCK)
        return pcm, pattern

    def test_all_channels_and_mono_are_bit_exact_through_wrap(self):
        pcm, pattern = self.capture(self.root, [2**32 - BLOCK, 0])
        self.assertEqual(pcm.frames, 1024)
        for name, channels, word in (("microphones.wav", 6, pattern), ("guitar.wav", 1, pattern[:3])):
            with wave.open(str(self.root / name)) as audio:
                self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (channels, 3, RATE))
                self.assertEqual(audio.readframes(1024), word * 1024)

    def test_new_hex_take_writes_wavs_and_mapping_in_display_order(self):
        writer = TakeWriter(self.root)
        pcm, pattern = self.capture(writer.path, [0, BLOCK], HEX_INPUTS)
        writer.finish(pcm)
        footer = json.loads((writer.path / "take.jsonl").read_text().splitlines()[-1])
        self.assertEqual(footer["fpga_channels"], [4, 5, 6, 1, 2, 3])
        for name, sample in (("microphones.wav", pattern[9:] + pattern[:9]),
                             ("guitar.wav", pattern[9:12])):
            with wave.open(str(writer.path / name)) as audio:
                self.assertEqual(audio.readframes(1024), sample * 1024)

    def test_pc_clock_brackets_first_sample_and_handles_midnight(self):
        now = datetime(2025, 1, 2, 6, tzinfo=timezone.utc)
        utc_ns = int(now.timestamp()) * 10**9 - 1_000_000
        span = (BLOCK-1) * 10**9 // RATE
        clock = TakeClock.from_packet(utc_ns, span + 4_000_000, BLOCK, RATE)
        self.assertEqual(clock.start_local.astimezone(timezone.utc), now + timedelta(milliseconds=1))
        self.assertEqual(clock.uncertainty_ms, 2)
        local = clock.start_local.astimezone(timezone(timedelta(hours=-6)))
        midnight = TakeClock(local, 2)
        self.assertEqual(midnight.ticks_since_midnight(RATE), 48)
        self.assertEqual(midnight.timecode(30), "00:00:00:00")
        self.assertEqual(TakeClock.load(midnight.metadata()), midnight)

    def test_both_wave_headers_have_identical_sample_time_references(self):
        pcm, _ = self.capture(self.root, [512])
        for name in ("guitar.wav", "microphones.wav"):
            data = (self.root/name).read_bytes()
            self.assertEqual(struct.unpack_from("<I", data, 4)[0], len(data)-8)
            self.assertEqual(data[12:16], b"bext")
            body = data[20:]
            self.assertEqual(body[320:330].decode(), pcm.clock.start_local.strftime("%Y-%m-%d"))
            self.assertEqual(struct.unpack_from("<Q", body, 338)[0], pcm.clock.ticks_since_midnight(RATE))

    @unittest.skipUnless(importlib.util.find_spec("PySide6") and shutil.which("gst-play-1.0"),
                         "Requires dashboard Python and GStreamer")
    def test_mix_includes_each_channel_at_one_sixth(self):
        from radar.replay import all_mics_sink
        source = self.root / "six.wav"
        target = self.root / "mix.wav"
        with wave.open(str(source), "wb") as f:
            f.setparams((6, 3, RATE, 0, "NONE", "not compressed"))
            for i in range(6):
                frame = bytearray(18)
                frame[i*3:i*3+3] = (0x300000).to_bytes(3, "little")
                f.writeframes(frame*4800)
        sink = all_mics_sink(f'audio/x-raw,format=S24LE ! wavenc ! filesink location="{target}"')
        subprocess.run(["gst-play-1.0", "-q", "--no-interactive", "--audiosink", sink, str(source)],
                       check=True, timeout=8)
        with wave.open(str(target)) as f:
            self.assertEqual(f.getnchannels(), 1)
            for i in range(6):
                f.setpos(i*4800+2400)
                self.assertAlmostEqual(int.from_bytes(f.readframes(1), "little", signed=True),
                                       0x300000//6, delta=2)

    def test_discontinuous_audio_reports_error_and_keeps_playable_prefix(self):
        with self.assertRaisesRegex(ValueError, "Missing FPGA samples"):
            self.capture(self.root, [0, BLOCK*2])
        with wave.open(str(self.root / "microphones.wav")) as audio:
            self.assertEqual(audio.getnframes(), BLOCK)

    @unittest.skipUnless(importlib.util.find_spec("PySide6"), "Run with the dashboard Python environment")
    def test_replay_uses_board_counter_and_preserves_gated_windows(self):
        from radar.gui import QApplication, Dashboard
        self.app = QApplication.instance() or QApplication([])
        with patch.object(Dashboard, "read_settings", return_value={}):
            window = Dashboard()
        window.persist = False
        self.addCleanup(window.close)
        writer = TakeWriter(self.root)
        first = 2**32 - BLOCK
        pcm, _ = self.capture(writer.path, [first, 0])
        frame = window.make_solver().demo(0, 1)
        for i, power in ((1, 0), (2, 4096 * 10000)):
            live = replace(frame, source="L", sequence=i, samples=(first+i*100) % 2**32,
                           energy=(power,)*6, scores=tuple(round(v) for v in frame.scores))
            window.accept_frame(live)
            writer.capture(window.polar, window.bearing.text(), live)
        writer.finish(pcm)
        take = Take.load(writer.path / "take.jsonl")
        self.assertEqual(take.duration, 1024/RATE)
        self.assertIsNone(take.frame_at(0))
        self.assertIsNone(take.frame_at(150/RATE)["result"])
        self.assertEqual(take.frame_at(250/RATE)["sequence"], 2)
        self.assertIsNone(take.frame_at(2))
        window.open_take(take.path)
        dialog = window.replay
        dialog.show_position(.01)
        self.assertEqual(dialog.bearing.text(), "Sound direction")
        self.assertEqual(dialog.polar.playback_time, .01)
        self.assertTrue(dialog.polar.result is not None)
        dialog.audio_source.setCurrentIndex(1)
        self.assertEqual(dialog.position, .01)
        self.assertEqual(dialog.audio_source.currentData(), "all")
        self.assertEqual(window.settings["replay_audio"], "all")
        self.assertEqual(take.clock.start_local, pcm.clock.start_local)
        self.assertAlmostEqual(take.clock.uncertainty_ms, pcm.clock.uncertainty_ms, delta=.00051)
        dialog.close()
        # Legacy takes have a valid sample timeline with no wall-clock anchor.
        rows = [json.loads(line) for line in take.path.read_text().splitlines()]
        del rows[-1]["clock"]
        take.path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        self.assertIsNone(Take.load(take.path).clock)
        window.open_take(take.path)
        self.assertEqual(window.replay.audio_source.currentData(), "all")
        window.replay.close()
        (writer.path / "microphones.wav").unlink()
        window.open_take(take.path)
        self.assertEqual(window.replay.audio_source.currentData(), "m1")
        self.assertFalse(window.replay.audio_source.model().item(1).isEnabled())
