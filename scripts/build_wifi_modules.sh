#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
embedded=$(realpath "${ZYBO_EMBEDDED:-$root/../fpga-dfx-hash-accelerator/build/embedded}")
out="$root/build/wifi"
kernel="$out/kernel"
cross="$embedded/rootfs/host/bin/arm-linux-"
release=$(cat "$kernel/include/config/kernel.release")
test "$release" = 6.6.40-dfx-hash-wifi
for name in hash vision; do mkdir -p "$out/$name-module"; done
cp "$embedded/module/"{Makefile,hash_accel.c,hash_accel.h} "$out/hash-module/"
cp "$root/../ZyboVision/software/linux/"{Makefile,zybovision_dma.c} "$out/vision-module/"
for name in hash vision; do
    make -C "$kernel" M="$out/$name-module" ARCH=arm CROSS_COMPILE="$cross" modules
done
stage=$(mktemp -d "$out/.modules.XXXXXX")
make -C "$kernel" ARCH=arm CROSS_COMPILE="$cross" INSTALL_MOD_PATH="$stage" INSTALL_MOD_STRIP=1 modules_install
extra="$stage/lib/modules/$release/extra"
mkdir -p "$extra"
cp "$out/hash-module/hash_accel.ko" "$out/vision-module/zybovision_dma.ko" "$extra/"
"${cross}strip" --strip-debug "$extra/"*.ko
find "$stage/lib/modules/$release" -maxdepth 1 -type l -name 'build' -delete
find "$stage/lib/modules/$release" -maxdepth 1 -type l -name 'source' -delete
depmod -b "$stage" "$release"
tar --owner=0 --group=0 -C "$stage/lib/modules" -czf "$out/wifi-modules.tar.gz" "$release"
sha256sum "$out/wifi-modules.tar.gz"
