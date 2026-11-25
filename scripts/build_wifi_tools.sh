#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
embedded=$(realpath "${ZYBO_EMBEDDED:-$root/../fpga-dfx-hash-accelerator/build/embedded}")
source=$(find "$embedded/sources" -maxdepth 1 -type d -name 'buildroot-*' -print -quit)
out="$root/build/wifi/userspace"
mkdir -p "$out"
sed -n '/^BR2_arm=y$/p; /^BR2_cortex_a9=/p; /^BR2_ARM_/p; /^BR2_TOOLCHAIN_EXTERNAL/p; /^# BR2_TOOLCHAIN_EXTERNAL_INET_RPC is not set$/p' "$embedded/buildroot.defconfig" > "$out/.config"
cat >> "$out/.config" <<'CONFIG'
BR2_JLEVEL=4
BR2_PACKAGE_IW=y
BR2_PACKAGE_WPA_SUPPLICANT=y
BR2_PACKAGE_WPA_SUPPLICANT_CLI=y
BR2_PACKAGE_WPA_SUPPLICANT_WPA3=y
CONFIG
make -C "$source" O="$out" olddefconfig
make -C "$source" O="$out" iw wpa_supplicant
