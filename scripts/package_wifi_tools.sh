#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
out="$root/build/wifi"
target="$out/userspace/target/usr"
strip="$out/userspace/host/bin/arm-linux-strip"
firmware="${WIFI_FIRMWARE_DIR:-/lib/firmware}"
mkdir -p "$out"
stage=$(mktemp -d "$out/.tools.XXXXXX")
trap 'rm -rf -- "$stage"' EXIT
mkdir -p "$stage/opt/zybo/wifi/"{bin,lib} "$stage/lib/firmware/mediatek" \
    "$stage/etc/init.d" "$stage/usr/sbin"
for name in iw wpa_cli wpa_supplicant; do
    binary=$(find "$target" -name "$name" -type f -print -quit)
    install -m 0755 "$binary" "$stage/opt/zybo/wifi/bin/$name"
done
for lib in libnl-3.so.200 libnl-genl-3.so.200; do
    install -m 0644 "$target/lib/$lib" "$stage/opt/zybo/wifi/lib/$lib"
done
"$strip" --strip-unneeded "$stage/opt/zybo/wifi/bin/"* "$stage/opt/zybo/wifi/lib/"*
if [[ -s "$firmware/mediatek/mt7610u.bin" ]]; then
    cp "$firmware/mediatek/mt7610u.bin" "$stage/lib/firmware/mediatek/"
else
    zstd -dc "$firmware/mediatek/mt7610u.bin.zst" > "$stage/lib/firmware/mediatek/mt7610u.bin"
fi
install -m 0644 "$firmware/regulatory.db" "$stage/lib/firmware/regulatory.db"
install -m 0755 "$root/software/wifi/"{connect-loop,wifi-dhcp} "$stage/opt/zybo/wifi/"
install -m 0755 "$root/software/wifi/S65zybo-wifi" "$stage/etc/init.d/"
install -m 0755 "$root/software/wifi/zybo-wifi" "$stage/usr/sbin/"
(cd "$stage" && find . -type f -print0 | sort -z | xargs -0 sha256sum > "$out/wifi-tools.SHA256")
tar --owner=0 --group=0 -C "$stage" -czf "$out/wifi-tools.tar.gz" .
(cd "$out" && sha256sum wifi-tools.tar.gz)
