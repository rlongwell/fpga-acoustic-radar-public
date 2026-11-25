#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
python3 -m unittest discover -s tests -p 'test_*.py' -v
mkdir -p build/sim
verilator --binary --timing -j 4 --Mdir build/sim --top-module tb_acoustic_radar \
    tests/tb_acoustic_radar.sv rtl/i2s_six.v rtl/correlator.v
build/sim/Vtb_acoustic_radar
verilator --binary --timing -j 4 --Mdir build/sim-pcm --top-module tb_pcm \
    tests/tb_pcm.sv rtl/radar_axi.v rtl/i2s_six.v rtl/correlator.v
build/sim-pcm/Vtb_pcm
