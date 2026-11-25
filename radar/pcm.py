"""Record the FPGA's sample-indexed six-channel PCM stream."""
import os
import select
import struct
import subprocess
import tempfile
import time
from contextlib import ExitStack

from .ethernet import ssh_command
from .protocol import FPGA_INPUTS
from .sync import TakeClock, broadcast_wave

RATE = 48_000
CHANNELS = 6
HEADER = struct.Struct("<4sIII")
BLOCK = 512


def sample_delta(index, origin):
    return ((index - origin + 2**31) % 2**32) - 2**31


class AudioCapture:
    def __init__(self, path, channel_order=FPGA_INPUTS):
        self.path = path
        self.channel_order = channel_order
        self.clock = None
        self.first = None
        self.frames = 0

    def run(self, host, transport, stopped):
        cmd = ssh_command(host, transport, pcm=True)
        with tempfile.TemporaryFile() as diagnostic, ExitStack() as stack:
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=diagnostic, bufsize=0)
            pending = bytearray()
            go_mono_ns = None
            stopping = None
            last = time.monotonic()
            try:
                while True:
                    now = time.monotonic()
                    if stopped() and stopping is None:
                        process.stdin.close()
                        stopping = now
                    if stopping is not None and now - stopping > 5:
                        raise TimeoutError("The Zybo did not finish the recording")
                    if now - last > 8:
                        raise TimeoutError("No microphone audio received over the network")
                    if not select.select([process.stdout], [], [], .1)[0]:
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired as error:
                            raise TimeoutError("Audio bridge did not close cleanly") from error
                        diagnostic.seek(0)
                        if process.returncode or stopping is None or pending:
                            reason = diagnostic.read(2048).decode(errors="replace").strip()
                            raise OSError(reason or "Zybo audio stream ended early")
                        break
                    received_ns = time.monotonic_ns()
                    last = now
                    pending.extend(chunk)
                    if go_mono_ns is None:
                        ready = b"PCM-READY\n"
                        if len(pending) < len(ready) and ready.startswith(pending):
                            continue
                        if pending != ready:
                            raise ValueError("Unexpected response while arming microphone audio")
                        pending.clear()
                        if stopping is None:
                            go_mono_ns = time.monotonic_ns()
                            go_utc_ns = time.time_ns()
                            process.stdin.write(b"go\n")
                        continue
                    while len(pending) >= HEADER.size:
                        magic, start, count, rate = HEADER.unpack_from(pending)
                        if (magic, count, rate) != (b"PCM6", BLOCK, RATE):
                            raise ValueError("Invalid six-microphone audio packet")
                        end = HEADER.size + count * CHANNELS * 3
                        if len(pending) < end:
                            break
                        if self.first is None:
                            self.clock = TakeClock.from_packet(go_utc_ns, received_ns - go_mono_ns, count, rate)
                            array = stack.enter_context(broadcast_wave(self.path / "microphones.wav", CHANNELS, rate, self.clock))
                            guitar = stack.enter_context(broadcast_wave(self.path / "guitar.wav", 1, rate, self.clock))
                            self.first = start
                        if start != (self.first + self.frames) % 2**32:
                            raise ValueError("Missing FPGA samples in the audio stream")
                        if (self.frames + count) * CHANNELS * 3 > 0xffffffff - 1024:
                            raise ValueError("Take reached the WAV size limit. Start another take.")
                        audio = pending[HEADER.size:end]
                        del pending[:end]
                        if self.channel_order != FPGA_INPUTS:
                            ordered = bytearray(len(audio))
                            stride = CHANNELS * 3
                            for mic, fpga_input in enumerate(self.channel_order):
                                for byte in range(3):
                                    ordered[mic*3 + byte::stride] = audio[fpga_input*3 + byte::stride]
                            audio = ordered
                        array.write(audio)
                        # Exact M1 samples, without array-summing phase cancellation.
                        mono = bytearray(count * 3)
                        for byte in range(3):
                            mono[byte::3] = audio[byte::CHANNELS * 3]
                        guitar.write(mono)
                        self.frames += count
            finally:
                process.stdin.close()
                process.stdout.close()
                if process.poll() is None:
                    process.kill()
                process.wait()
