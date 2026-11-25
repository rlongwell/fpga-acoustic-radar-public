"""Exclusive sessions on the Zybo's existing Linux serial console."""
import errno
from pathlib import Path
import re
import subprocess
import time

import serial

PORT = "auto"
SERIAL_BY_ID = Path("/dev/serial/by-id")
LOGIN = rb"zybo login: $"
PROMPT = rb"(?:^|\n)\r*# $"
STREAM = b"/opt/zybo/radar/radar-stream"
BOOTLOADER = re.compile(rb"U-Boot (?:SPL )?\d{4}\.|Hit any key to stop autoboot|(?:^|\n)\r*(?:Zynq|zynq-uboot|=>)>? $")
BOOT_STAGE = re.compile(rb"(?P<loader>" + BOOTLOADER.pattern + rb")|Starting kernel \.\.\.|Linux version \d")
# The saved Zybo boot log has a two-second autoboot countdown. Allow a
# longer silent interval when attaching after a getty has printed its prompt.
IDLE_PROBE_SECONDS = 10


class Console:
    def __init__(self, port=PORT):
        self.port = port
        self.pending = bytearray()

    def __enter__(self):
        port = self.port
        if port == "auto":
            matches = sorted(SERIAL_BY_ID.glob("usb-Digilent_*-if01-port0"))
            if not matches:
                raise FileNotFoundError(errno.ENOENT, "No Digilent USB UART found")
            if len(matches) > 1:
                raise ValueError("Multiple Digilent UARTs found. Select a device with --port: "
                                 + ", ".join(map(str, matches)))
            port = str(matches[0])
        if subprocess.run(["fuser", port], capture_output=True).returncode == 0:
            raise OSError("The Zybo UART is in use. Close the other serial application.")
        self.link = serial.Serial(port, 115200, timeout=0.12, write_timeout=3, exclusive=True)
        return self

    def __exit__(self, *exc):
        self.link.close()

    def send(self, data):
        self.link.write(data)
        self.link.flush()

    def expect(self, pattern, timeout=8):
        match_pattern = re.compile(pattern)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            match = match_pattern.search(self.pending)
            if match:
                prefix = bytes(self.pending[:match.end()])
                del self.pending[:match.end()]
                return prefix
            self.pending.extend(self.link.read(self.link.in_waiting or 1))
            if len(self.pending) > 32768:
                del self.pending[:-8192]
        raise TimeoutError("Zybo console did not reply")

    def login(self):
        self.send(b"\r")
        self.expect(LOGIN)
        self.send(b"root\r")
        self.expect(PROMPT)

    def wait_for_shell(self, stopped):
        """Attach to an existing Linux shell or getty, including during boot."""
        idle_since = time.monotonic()
        in_bootloader = False
        while not stopped():
            while match := BOOT_STAGE.search(self.pending):
                in_bootloader = match.lastgroup == "loader"
                del self.pending[:match.end()]
            if re.search(PROMPT, self.pending):
                self.pending.clear()
                return True
            if re.search(LOGIN, self.pending):
                self.pending.clear()
                in_bootloader = False
                self.send(b"root\r")
                idle_since = time.monotonic()

            chunk = self.link.read(self.link.in_waiting or 1)
            if chunk:
                self.pending.extend(chunk)
                del self.pending[:-4096]
                idle_since = time.monotonic()
            elif not in_bootloader and time.monotonic() - idle_since >= IDLE_PROBE_SECONDS and not stopped():
                # A running, quiet getty (or shell) may already have printed
                # the prompt before USB was opened. Ask it to redraw once idle.
                self.send(b"\r")
                idle_since = time.monotonic()
        return False

    def logout(self):
        self.send(b"exit\r")
        self.expect(LOGIN, 4)

    def line(self, timeout=0.2):
        try:
            return self.expect(rb"\n", timeout).rstrip(b"\r\n")
        except TimeoutError:
            return b""
