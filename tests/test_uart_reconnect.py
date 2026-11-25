"""Exercise the dashboard, serial protocol and Linux USB hotplug path together."""
import base64
import errno
import importlib.util
import os
from pathlib import Path
import pty
import tempfile
import time
import tty
import unittest
from unittest.mock import patch
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    from PySide6.QtWidgets import QApplication
    from radar import gui, uart


@unittest.skipUnless(HAS_QT, "Use .venv/bin/python for GUI tests")
class PortDiscoveryTest(unittest.TestCase):
    def test_auto_uses_only_one_digilent_uart(self):
        with tempfile.TemporaryDirectory() as directory:
            devices = Path(directory)
            (devices / "usb-Digilent_boardA-if00-port0").touch()
            with patch.object(uart, "SERIAL_BY_ID", devices):
                with self.assertRaises(FileNotFoundError):
                    with uart.Console("auto"):
                        pass
                port = devices / "usb-Digilent_boardA-if01-port0"
                port.touch()
                with patch.object(uart.serial, "Serial") as serial:
                    with uart.Console("auto"):
                        pass
                    self.assertEqual(serial.call_args.args[0], str(port))
                (devices / "usb-Digilent_boardB-if01-port0").touch()
                with self.assertRaisesRegex(ValueError, "Multiple Digilent UARTs"):
                    with uart.Console("auto"):
                        pass


@unittest.skipUnless(HAS_QT, "Use .venv/bin/python for GUI tests")
class ReconnectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.port = Path(directory.name) / "zybo-uart"
        self.master = None
        self.addCleanup(self.unplug)
        self.buffer = bytearray()
        for setting in (patch.object(gui, "SETTINGS", self.port.with_suffix(".json")),
                        patch.object(gui.UARTReader, "retry_seconds", 0.05),
                        patch.object(uart, "IDLE_PROBE_SECONDS", 0.45)):
            setting.start()
            self.addCleanup(setting.stop)
        self.window = gui.Dashboard(port=str(self.port))
        self.addCleanup(self.window.close)
        self.window.connect_board()

    def wait_for(self, condition, timeout=3):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.processEvents()
            if condition():
                return
            time.sleep(0.01)
        self.fail(f"Condition timed out. Dashboard shows {self.window.status.text()!r}, UART {self.buffer!r}")

    def status(self, prefix):
        self.wait_for(lambda: self.window.status.text().startswith(prefix))

    def plug(self):
        self.master, slave = pty.openpty()
        tty.setraw(slave)
        os.set_blocking(self.master, False)
        self.port.symlink_to(os.ttyname(slave))
        os.close(slave)
        self.buffer.clear()

    def unplug(self):
        self.port.unlink(missing_ok=True)
        if self.master is not None:
            os.close(self.master)
            self.master = None

    def send(self, line):
        os.write(self.master, line)

    def read(self):
        try:
            self.buffer.extend(os.read(self.master, 8192))
        except BlockingIOError:
            pass
        except OSError as error:
            if error.errno != errno.EIO:  # Slave not open.
                raise
        return self.buffer

    def expect(self, command):
        self.wait_for(lambda: len(self.read()) >= len(command))
        self.assertEqual(bytes(self.buffer), command)
        self.buffer.clear()

    def silent(self, duration):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.app.processEvents()
            self.assertFalse(self.read(), "Dashboard transmitted during boot or while paused")
            time.sleep(0.01)

    def login(self):
        self.send(b"\r\nzybo login: ")
        self.expect(b"root\r")
        self.shell()

    def shell(self):
        self.send(b"\r\n# ")
        self.expect(uart.STREAM + b" --stream\r")

    def frame(self, sequence):
        data = b"AR1 L %d 4096 0 1200,1200,1200,1200,1200,1200 " % sequence + base64.b64encode(bytes(975))
        self.send(data + b" %08x\r\n" % zlib.crc32(data))
        self.status(f"Connected · FPGA live · window {sequence}")

    def test_power_cycles_and_reboot_keep_same_dashboard(self):
        self.status("Waiting for Zybo USB")
        for sequence in (31, 1):
            self.plug()
            self.status("Waiting for Zybo Linux")
            self.send(b"\r\nU-Bo")
            time.sleep(0.02)
            self.send(b"ot SPL 2024.01\r\nHit any key to stop autoboot: 2")
            self.silent(0.65)  # Longer than the idle-getty probe interval.
            self.login()
            self.frame(sequence)
            if sequence == 31:
                self.unplug()
                self.status("Waiting for Zybo USB")
                self.assertIsNone(self.window.frame)
                self.assertIsNone(self.window.polar.result)
                self.assertEqual(self.window.array_level.text(), "Array: -- dB")

        # A warm reboot can leave the same USB tty present for the entire boot.
        self.send(b"\r\nU-Boot 2024.01\r\nHit any key to stop autoboot: 2")
        self.status("Waiting for Zybo Linux")
        self.silent(2.2)  # Includes a full former stream heartbeat interval.
        self.login()
        self.frame(12)
        self.window.connect_button.click()
        self.expect(b"\x03")
        self.send(b"RADAR-END\r\n# ")
        self.expect(b"exit\r")
        self.send(b"\r\nzybo login: ")
        self.status("Disconnected")
        self.unplug()
        self.plug()
        self.silent(0.6)
        self.assertIsNone(self.window.worker)

    def test_busy_port_and_quiet_already_booted_shell(self):
        self.status("Waiting for Zybo USB")
        # Create the link only after taking ownership of the new tty.
        self.master, slave = pty.openpty()
        try:
            tty.setraw(slave)
            os.set_blocking(self.master, False)
            self.port.symlink_to(os.ttyname(slave))
            self.status("The Zybo UART is in use")
            self.silent(0.55)
        finally:
            os.close(slave)
        self.status("Waiting for Zybo Linux")
        self.expect(b"\r")
        self.shell()
        self.frame(9)
        self.unplug()
        self.status("Waiting for Zybo USB")
        self.window.demo_button.click()
        self.wait_for(lambda: self.window.worker is None)
        self.assertEqual(self.window.frame.source, "D")
        self.plug()
        self.silent(0.6)
        self.assertTrue(self.window.demo_button.isChecked())

    def test_stream_stall_recovers_on_same_tty(self):
        self.status("Waiting for Zybo USB")
        self.plug()
        self.status("Waiting for Zybo Linux")
        self.login()
        self.frame(42)
        # A stalled stream can leave the FTDI interface fully enumerated.
        self.window.worker.frame_timeout = 1.3
        self.wait_for(lambda: self.window.frame is None)
        self.status("Waiting for Zybo Linux")
        self.expect(b"\r")  # Safe idle-shell probe after the stream times out.
        self.shell()
        self.frame(1)
        self.unplug()
        self.status("Waiting for Zybo USB")
