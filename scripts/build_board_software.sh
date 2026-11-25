#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
embedded="${ZYBO_EMBEDDED:-$root/../fpga-dfx-hash-accelerator/build/embedded}"
compiler="${CC_ARM:-$embedded/rootfs/host/bin/arm-linux-gcc}"
dt_dir="${DTC_DIR:-$embedded/kernel/scripts/dtc}"
mkimage="${MKIMAGE:-$embedded/uboot/tools/mkimage}"
base="${ZYBO_RESCUE_DTB:-$root/../zybo-shared-sd/out-menu/boot/profiles/rescue/system.dtb}"
output="$root/build/board"
mkdir -p "$output"
"$compiler" -std=c11 -O2 -Wall -Wextra -Werror "$root/software/radar_stream.c" -lm -o "$output/radar-stream"
"$dt_dir/dtc" -@ -I dts -O dtb -o "$output/radar-overlay.dtbo" "$root/software/radar-overlay.dts"
"$dt_dir/fdtoverlay" -i "$base" -o "$output/system.dtb" "$output/radar-overlay.dtbo"
"$mkimage" -A arm -T script -C none -n 'Zybo acoustic radar' -d "$root/software/boot-radar.cmd" "$output/radar.scr"
(cd "$output" && sha256sum system.dtb radar.scr radar-stream > SHA256SUMS)
