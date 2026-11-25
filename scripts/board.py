#!/usr/bin/env python3
"""Boot the staged radar profile for this session or run its board self-test."""
import argparse
import re
import shlex
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from radar.protocol import Frame
from radar.uart import Console, LOGIN, PORT, PROMPT, STREAM


def boot(console):
    verified = command(console, b"cd /boot/profiles/radar && sha256sum -c SHA256SUMS")
    if any(filename + b": OK" not in verified for filename in (b"system.bit", b"system.dtb", b"radar.scr")):
        raise RuntimeError("The radar files on the SD card did not pass verification")
    console.send(b"reboot\r")
    prior = console.expect(rb"Hit any key to stop autoboot:", 35)
    print(prior.decode(errors="replace"), end="")
    console.send(b" ")
    console.expect(rb"(?:^|\n)\r*(?:Zynq|zynq-uboot|=>)>? $", 4)
    console.send(b'if fatload mmc 0:1 0x03100000 profiles/radar/radar.scr; then source 0x03100000; fi\r')
    record = console.expect(rb"(?m)^FPGA bitstream: profiles/radar/system\.bit\r*\n", 20)
    print(record.decode(errors="replace"), end="")
    print(console.expect(LOGIN, 90).decode(errors="replace"), end="")


def install(console, path):
    if not re.fullmatch(r"/root/acoustic-radar-[a-z0-9-]+\.tar\.gz", path):
        raise ValueError("Invalid radar bundle path")
    archive = shlex.quote(path)
    line = ('work=$(mktemp -d /root/.radar-install.XXXXXX) && '
            f'gzip -dc {archive} > "$work/bundle.tar" && '
            'tar -xf "$work/bundle.tar" -C "$work" && '
            'sh "$work/install.sh" "$work"; code=$?; '
            'if [ -n "$work" ]; then rm -rf "$work"; fi; '
            'printf "\\nRADAR-INSTALL-%s\\n" "$code"')
    output = command(console, line.encode(), 30)
    if b"\nRADAR-INSTALL-0\r" not in output:
        raise RuntimeError("The on-board installer did not finish successfully")


def command(console, line, timeout=12):
    console.send(line + b"\r")
    data = console.expect(PROMPT, timeout)
    print(data.decode(errors="replace"), end="")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("boot", "check", "self-test", "capture", "install"))
    parser.add_argument("--bundle", help="Board-side path to a verified deployment bundle")
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--windows", type=int, choices=range(1, 26), default=1,
                        metavar="1-25", help="Number of live packets to capture")
    args = parser.parse_args()
    if args.action == "install" and not args.bundle:
        parser.error("install requires --bundle")
    try:
        with Console(args.port) as console:
            console.login()
            if args.action == "boot":
                boot(console)
                console.login()
            try:
                if args.action == "install":
                    install(console, args.bundle)
                elif args.action == "self-test":
                    evidence = command(console, STREAM + b" --self-test")
                    packet = next(line for line in evidence.splitlines() if line.startswith(b"AR1 "))
                    if Frame.parse(packet).source != "T" or b"RADAR-SELFTEST PASS 15 pairs" not in evidence:
                        raise RuntimeError("The FPGA self-test failed")
                elif args.action == "capture":
                    console.send(STREAM + b" --stream\r")
                    try:
                        for _ in range(args.windows):
                            data = console.expect(rb"(?:^|\n)(AR1 [^\r\n]+)\r*\n", 5)
                            raw = re.search(rb"(?m)^AR1 [^\r\n]+", data)[0]
                            frame = Frame.parse(raw)
                            if frame.source != "L":
                                raise RuntimeError("Unexpected non-live packet")
                            print(f"Live packet {frame.sequence}, frames={frame.samples}, "
                                  f"dropped={frame.dropped}, energy={frame.energy}")
                    finally:
                        console.send(b"\x03")
                        console.expect(PROMPT, 4)
                else:
                    evidence = command(console, STREAM + b" --check; cat /proc/cmdline")
                    if b"RADAR-READY" not in evidence or b"zybo.profile=radar" not in evidence:
                        raise RuntimeError("Radar profile or registers were unavailable")
            finally:
                console.logout()
    except (OSError, ValueError, RuntimeError, StopIteration) as error:
        print(f"Radar board: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
