"""Read live FPGA snapshots over the Zybo's authenticated network link."""
import os
import json
from pathlib import Path
import select
import subprocess
import time

from .protocol import Frame

HOST = "zybo-wired"
WIFI_HOST = "zybo-wifi"
INTERFACES = {"ethernet": "eth0", "wifi": "wlan0"}


def stream_command(transport, pcm=False):
    # Check the address SSH accepted and the return route to this client.
    interface = INTERFACES[transport]
    identify = 'echo PCM-READY; IFS= read -r go || exit 0; ' if pcm else 'echo "RADAR-LINK $1"; '
    return (
        'set -- $SSH_CONNECTION; '
        f'if [ "$#" != 4 ] || ! ip addr show dev {interface} | grep -Fq " $3/" '
        f'|| ! ip route get "$1" from "$3" | grep -Fq " dev {interface} "; then '
        f'echo "RADAR-ERROR SSH must use the Zybo {interface} interface" >&2; exit 1; fi; '
        f'{identify}exec /opt/zybo/radar/radar-stream {"--pcm" if pcm else "--ethernet"}'
    )


def ssh_command(host, transport, pcm=False):
    if not host or host.startswith("-") or any(c.isspace() for c in host):
        raise ValueError("Enter the Zybo SSH host")
    return ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ClearAllForwardings=yes", "-o", "ConnectTimeout=3",
               "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=2",
               "--", host, stream_command(transport, pcm)]


def pc_link(address):
    # Use the local address observed on the far end of this specific SSH socket.
    try:
        data = subprocess.check_output(["ip", "-j", "address", "show"], timeout=2)
        for dev in json.loads(data):
            if any(a.get("local") == address for a in dev.get("addr_info", ())):
                sysdev = Path("/sys/class/net") / dev["ifname"]
                physical = next(sysdev.glob("lower_*"), sysdev).resolve()
                if (physical / "wireless").exists():
                    return "PC Wi-Fi"
                if (physical / "device").exists() and dev.get("link_type") == "ether":
                    return "PC Ethernet"
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return ""


def live_frames(host, stopped, transport="ethernet", link_changed=None, keep_all=None):
    command = ssh_command(host, transport)
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, bufsize=0) as process:
        pending = bytearray()
        last_frame = heartbeat = time.monotonic()
        diagnostic = "SSH connection closed"
        try:
            while not stopped():
                if select.select([process.stdout], [], [], 0.15)[0]:
                    chunk = os.read(process.stdout.fileno(), 16384)
                    if not chunk:
                        raise ConnectionError(diagnostic)
                    pending.extend(chunk)
                    if len(pending) > 32768:
                        raise ValueError("Incomplete radar frame over SSH")
                    lines = pending.split(b"\n")
                    pending = lines.pop()
                    batch = []
                    for line in lines:
                        if line.startswith(b"AR1 "):
                            try:
                                frame = Frame.parse(bytes(line))
                            except ValueError:
                                continue
                            if frame.source == "L":
                                batch.append(frame)
                        elif line.startswith(b"RADAR-LINK ") and link_changed:
                            link_changed(pc_link(line[11:].strip().decode("ascii")))
                        elif line.strip():
                            diagnostic = line.decode(errors="replace").strip()[:350]
                            if line.startswith(b"RADAR-ERROR"):
                                raise RuntimeError(diagnostic)
                    if batch:
                        last_frame = time.monotonic()
                        if last_frame - heartbeat >= 2:
                            process.stdin.write(b"\n")
                            heartbeat = last_frame
                        yield from batch if keep_all and keep_all() else batch[-1:]
                if time.monotonic() - last_frame > 6:
                    raise TimeoutError("No live radar frames over SSH")
        finally:
            # EOF lets the bridge release the FPGA before the next session.
            process.stdin.close()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
