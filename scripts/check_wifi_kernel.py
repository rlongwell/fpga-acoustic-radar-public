#!/usr/bin/env python3
"""Verify candidate kernel module exports against the drivers it will load."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/wifi"
RELEASE = "6.6.40-dfx-hash-wifi"


def main():
    kernel = OUT / "kernel"
    if (kernel / "include/config/kernel.release").read_text().strip() != RELEASE:
        raise RuntimeError("Unexpected Wi-Fi kernel release")
    symbols = {row.split()[1]: row.split()[0] for row in
               (kernel / "Module.symvers").read_text().splitlines()}
    names = (ROOT.parent / "zybo-shared-sd/build/audio-rootfs/opt/zybo").glob("*/*.ko")
    modules = [*names, *OUT.glob("*-module/*.ko")]
    if len(modules) != 4:
        raise RuntimeError("Expected drivers for hash, vision, FX, and Chain4")
    for module in modules:
        imports = [line.split() for line in subprocess.check_output(
            ["modprobe", "--show-modversions", module], text=True).splitlines()]
        bad = [name for crc, name in imports if symbols.get(name) != crc]
        if not imports or bad:
            raise RuntimeError(f"{module}: incompatible module version imports: {bad}")
        print(f"{module}: all {len(imports)} versioned imports match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
