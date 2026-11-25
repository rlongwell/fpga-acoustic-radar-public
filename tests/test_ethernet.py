"""Drive the actual GUI reader through a local stand-in for the network SSH process."""
import base64
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    from PySide6.QtWidgets import QApplication
    from radar import ethernet, gui


def packet(sequence):
    body = b"AR1 L %d 4096 0 1200,1200,1200,1200,1200,1200 " % sequence + base64.b64encode(bytes(975))
    return body + b" %08x\n" % zlib.crc32(body)


@unittest.skipUnless(HAS_QT, "Use .venv/bin/python for GUI tests")
class NetworkDashboardTest(unittest.TestCase):
    def test_wired_default_retries_without_using_uart(self):
        self.check_connection("ethernet", "Ethernet", ethernet.HOST, "eth0")

    def test_wifi_retries_and_remembers_transport(self):
        self.check_connection("wifi", "Wi-Fi", ethernet.WIFI_HOST, "wlan0")

    def test_recording_preserves_windows_batched_by_ssh(self):
        real_popen = subprocess.Popen
        stream = b"RADAR-LINK 192.0.2.22\n" + packet(10) + packet(11)
        def peer(args, **kwargs):
            return real_popen([sys.executable, "-uc",
                f"import os;os.write(1,{stream!r});os.read(0,1)"], **kwargs)
        for recording in (True, False):
            links = []
            with patch.object(ethernet.subprocess, "Popen", peer), patch.object(ethernet, "pc_link", return_value="PC Ethernet") as detect:
                frames = ethernet.live_frames("board", lambda: False, "wifi", links.append, lambda: recording)
                try:
                    self.assertEqual(next(frames).sequence, 10 if recording else 11)
                    if recording:
                        self.assertEqual(next(frames).sequence, 11)
                    self.assertEqual(links, ["PC Ethernet"])
                    detect.assert_called_once_with("192.0.2.22")
                finally:
                    frames.close()

    def check_connection(self, mode, label, host, interface):
        app = QApplication.instance() or QApplication([])
        real_popen = subprocess.Popen
        calls = []
        def peer(args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                source = f'print("RADAR-ERROR SSH must use the Zybo {interface} interface")'
            else:
                # Split a packet across reads, with a bad CRC immediately before it.
                wire = packet(3).replace(b'AR1 L', b'AR1 T') + packet(28)
                source = (f'import os, time; wire={wire!r}; '
                          'os.write(1, wire[:-20]); time.sleep(.1); os.write(1, wire[-20:]); '
                          'os.read(0, 1024)')
            return real_popen([sys.executable, "-uc", source], **kwargs)

        with tempfile.TemporaryDirectory() as directory, patch.object(gui, "SETTINGS", Path(directory)/"gui.json"), \
             patch.object(gui.NetworkReader, "retry_seconds", .15), patch.object(ethernet.subprocess, "Popen", peer), \
             patch.object(gui.UARTReader, "start", side_effect=AssertionError("unexpected UART access")):
            w = gui.Dashboard(wifi_host="" if mode == "wifi" else None)
            try:
                w.connect_board()
                seen_error = False
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and w.frame is None:
                    app.processEvents()
                    seen_error |= f"{interface} interface" in w.status.text()
                    time.sleep(.005)
                self.assertTrue(seen_error)
                self.assertIsNotNone(w.frame)
                self.assertEqual(w.frame.sequence, 28)
                self.assertIn(label, w.status.text())
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0][-2], host)
                self.assertIn(f"ip addr show dev {interface} ", calls[0][-1])
                self.assertIn(f" dev {interface} ", calls[0][-1])
                self.assertEqual(gui.Dashboard.read_settings()["transport"], mode)
                self.assertIn("StrictHostKeyChecking=yes", calls[0])
                w.connect_button.click()
                deadline = time.monotonic() + 3
                while w.worker and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                self.assertIsNone(w.worker)
            finally:
                w.close()
