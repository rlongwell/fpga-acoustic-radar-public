#!/bin/sh
set -eu
source_dir="$1"
cd "$source_dir"
sha256sum -c SHA256SUMS
grep -q ' /boot vfat ' /proc/mounts
mkdir -p /boot/profiles /opt/zybo
boot_stage="$(mktemp -d /boot/profiles/.radar-stage.XXXXXX)"
app_stage="$(mktemp -d /opt/zybo/.radar-stage.XXXXXX)"
trap 'rm -rf "$boot_stage" "$app_stage"' EXIT
cp system.bit system.dtb radar.scr "$boot_stage/"
cp radar-stream "$app_stage/"
chmod 0755 "$app_stage/radar-stream"
(cd "$boot_stage" && sha256sum system.bit system.dtb radar.scr > SHA256SUMS)
# Back up only a previous radar installation. The shared boot files stay in place.
stamp="$(date +%s)"
if [ -e /boot/profiles/radar ]; then
    mv /boot/profiles/radar "/boot/profiles/radar.previous.$stamp"
fi
if [ -e /opt/zybo/radar ]; then
    mv /opt/zybo/radar "/opt/zybo/radar.previous.$stamp"
fi
mv "$boot_stage" /boot/profiles/radar
mv "$app_stage" /opt/zybo/radar
sync
(cd /boot/profiles/radar && sha256sum -c SHA256SUMS && sha256sum system.bit)
