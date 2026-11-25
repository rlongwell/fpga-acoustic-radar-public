#!/usr/bin/env python3
"""Stage the verified Wi-Fi tools and one-time test kernel on the in-board SD card."""
import argparse
import hashlib
from pathlib import Path
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from radar.uart import Console, LOGIN, PROMPT

OUT = ROOT / "build/wifi"
CANDIDATE = "/boot/zImage.wifi-candidate"
TEST_SCRIPT = "/boot/wifi-test.scr"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked(console, shell, timeout=25):
    console.send(f"{shell}; result=$?; printf '\\nWIFI-COMMAND-%s\\n' \"$result\"\r".encode())
    message = console.expect(rb"(?m)^WIFI-COMMAND-(\d+)\r*\n", timeout)
    console.expect(PROMPT, 5)
    print(message.decode(errors="replace"), end="")
    if not re.search(rb"(?m)^WIFI-COMMAND-0\r*$", message):
        raise RuntimeError("Board command failed")
    return message


def install(console, archive):
    if not re.fullmatch(r"/root/wifi-tools-[a-f0-9]{12}\.tar\.gz", archive):
        raise ValueError("Expected /root/wifi-tools-<12 hex characters>.tar.gz")
    digest = sha(OUT / "wifi-tools.tar.gz")
    checked(console, f"printf '%s\\n' '{digest}  {shlex.quote(archive)}' | sha256sum -c - && "
            f"w=$(mktemp -d /tmp/.zybo-wifi.XXXXXX) && gzip -dc {shlex.quote(archive)} > \"$w/tools.tar\" && tar -xf \"$w/tools.tar\" -C \"$w\" && "
            'mkdir -p /lib/firmware/mediatek /opt/zybo/wifi && '
            'cp -Rp "$w/opt/zybo/wifi/." /opt/zybo/wifi/ && '
            'cp -p "$w/lib/firmware/regulatory.db" /lib/firmware/ && '
            'cp -p "$w/lib/firmware/mediatek/mt7610u.bin" /lib/firmware/mediatek/ && '
            'cp -p "$w/usr/sbin/zybo-wifi" /usr/sbin/ && '
            'cp -p "$w/etc/init.d/S65zybo-wifi" /etc/init.d/ && sync && '
            "LD_LIBRARY_PATH=/opt/zybo/wifi/lib /opt/zybo/wifi/bin/wpa_supplicant -v && "
            "LD_LIBRARY_PATH=/opt/zybo/wifi/lib /opt/zybo/wifi/bin/iw --version")


def install_modules(console, archive):
    if not re.fullmatch(r"/root/wifi-modules-[a-f0-9]{12}\.tar\.gz", archive):
        raise ValueError("Expected a checksum-tagged module archive")
    digest = sha(OUT / "wifi-modules.tar.gz")
    quoted = shlex.quote(archive)
    release = "6.6.40-dfx-hash-wifi"
    checked(console, f"printf '%s\\n' '{digest}  {quoted}' | sha256sum -c - && "
            "w=$(mktemp -d /lib/modules/.wifi.XXXXXX) && "
            f'gzip -dc {quoted} > "$w/modules.tar" && tar -xf "$w/modules.tar" -C "$w" && '
            f'test ! -e /lib/modules/{release} && mv "$w/{release}" /lib/modules/ && '
            f'test -s /lib/modules/{release}/extra/hash_accel.ko && '
            f'test -s /lib/modules/{release}/extra/zybovision_dma.ko && sync', 40)


def test_boot(console):
    digest = sha(OUT / "kernel/arch/arm/boot/zImage")
    script_digest = sha(OUT / "wifi-test.scr")
    checked(console, f"printf '%s\\n' '{digest}  {CANDIDATE}' '{script_digest}  {TEST_SCRIPT}' | sha256sum -c -")
    console.send(b"reboot\r")
    print(console.expect(rb"Hit any key to stop autoboot:", 35).decode(errors="replace"), end="")
    console.send(b" ")
    console.expect(rb"(?:^|\n)\r*(?:Zynq|zynq-uboot|=>)>? $", 5)
    console.send(b'if fatload mmc 0:1 0x03100000 wifi-test.scr; then source 0x03100000; fi\r')
    print(console.expect(LOGIN, 50).decode(errors="replace"), end="")
    console.login()
    checked(console, "test -d /sys/bus/usb/drivers/mt76x0u && "
            "test -s /lib/firmware/mediatek/mt7610u.bin && "
            "zybo-wifi status && /opt/zybo/radar/radar-stream --check")


def promote(console):
    digest = sha(OUT / "kernel/arch/arm/boot/zImage")
    checked(console, "test -d /sys/bus/usb/drivers/mt76x0u && mountpoint -q /boot && "
            "test \"$(uname -r)\" = 6.6.40-dfx-hash-wifi && "
            "test -s /lib/modules/6.6.40-dfx-hash-wifi/extra/hash_accel.ko && "
            "test -s /lib/modules/6.6.40-dfx-hash-wifi/extra/zybovision_dma.ko && "
            f"printf '%s\\n' '{digest}  {CANDIDATE}' | sha256sum -c - && "
            "test ! -e /boot/zImage.pre-wifi && cp /boot/zImage /boot/zImage.pre-wifi && "
            "cmp /boot/zImage /boot/zImage.pre-wifi && sync && "
            f"mv -f {CANDIDATE} /boot/zImage && sync && sha256sum /boot/zImage /boot/zImage.pre-wifi")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install-tools", "install-modules", "test-boot", "promote", "verify-default"))
    parser.add_argument("--archive", default="")
    args = parser.parse_args()
    with Console() as console:
        console.login()
        try:
            if args.action == "install-tools":
                install(console, args.archive)
            elif args.action == "install-modules":
                install_modules(console, args.archive)
            elif args.action == "test-boot":
                test_boot(console)
            elif args.action == "promote":
                promote(console)
            else:
                console.send(b"reboot\r")
                print(console.expect(LOGIN, 80).decode(errors="replace"), end="")
                console.login()
                checked(console, "zybo-profile status && zybo-wifi status && "
                        "test -d /sys/bus/usb/drivers/mt76x0u && "
                        "if grep -q 'zybo.profile=hash' /proc/cmdline; then "
                        "/opt/zybo/hash/start.sh status && test -d /sys/module/hash_accel; fi")
        finally:
            try:
                console.logout()
            except TimeoutError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
