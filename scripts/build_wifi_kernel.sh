#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
embedded=$(realpath "${ZYBO_EMBEDDED:-$root/../fpga-dfx-hash-accelerator/build/embedded}")
out="$root/build/wifi/kernel"
source=$(find "$embedded/sources" -maxdepth 1 -type d -name 'linux-xlnx-*' -print -quit)
cross="$embedded/rootfs/host/bin/arm-linux-"
firmware="${WIFI_FIRMWARE_DIR:-/lib/firmware}"
# USB can enumerate before the SD root is mounted, so embed these two files.
fw="$root/build/wifi/firmware"
mkdir -p "$out" "$fw/mediatek"
if [[ -s "$firmware/mediatek/mt7610u.bin" ]]; then
    cp "$firmware/mediatek/mt7610u.bin" "$fw/mediatek/"
else
    zstd -dc "$firmware/mediatek/mt7610u.bin.zst" > "$fw/mediatek/mt7610u.bin"
fi
install -m 0644 "$firmware/regulatory.db" "$fw/regulatory.db"
cp "$embedded/kernel/.config" "$out/.config"
"$source/scripts/config" --file "$out/.config" --keep-case \
    --set-str EXTRA_FIRMWARE 'mediatek/mt7610u.bin regulatory.db' \
    --set-str EXTRA_FIRMWARE_DIR "$fw" \
    --set-str LOCALVERSION '-dfx-hash-wifi'  \
    --disable KERNEL_GZIP --enable KERNEL_XZ \
    --enable CFG80211 --enable CFG80211_CERTIFICATION_ONUS --disable CFG80211_REQUIRE_SIGNED_REGDB \
    --disable CFG80211_REG_RELAX_NO_IR --disable CFG80211_REG_CELLULAR_HINTS --enable MAC80211 --enable MT76x0U \
    --enable RFKILL --enable USB_CHIPIDEA_HOST
make -C "$source" O="$out" ARCH=arm CROSS_COMPILE="$cross" olddefconfig
for option in CFG80211 MAC80211 MT76x0U USB_CHIPIDEA_HOST UIO_PDRV_GENIRQ KERNEL_XZ; do
    grep -qx "CONFIG_${option}=y" "$out/.config"
done
make -C "$source" O="$out" ARCH=arm CROSS_COMPILE="$cross" -j "${KERNEL_JOBS:-8}" zImage modules
