#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
vivado="${VIVADO:-$(command -v vivado || echo /opt/amd/xilinx/Vivado/2024.2/bin/vivado)}"
if [[ ! -x "$vivado" ]]; then
    printf 'Set VIVADO to the Vivado 2024.2 executable.\n' >&2
    exit 1
fi
mkdir -p "$root/build"
cd "$root/build"
rm -f bitstream.SHA256
"$vivado" -mode batch -nolog -nojournal -source "$root/scripts/build_fpga.tcl"
sha256sum system.bit > bitstream.SHA256
