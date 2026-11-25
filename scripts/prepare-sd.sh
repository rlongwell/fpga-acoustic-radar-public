#!/usr/bin/env bash
# Assemble a dedicated Zybo Z7-20 radar card as an ordinary disk image.
set -euo pipefail
usage() {
    echo 'Usage: ./scripts/prepare-sd.sh [--built]'
    echo 'Writes build/radar-sd.img. Default: released six-mic bitstream.'
    echo 'Use --built after ./build.sh. Set RADAR_BSP to an already downloaded Digilent 2022.1 BSP.'
}
case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    ''|--built) ;;
    *) usage >&2; exit 2 ;;
esac
(( $# <= 1 )) || { usage >&2; exit 2; }
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
out="$root/build"
release="$root/releases/six-mic-recording"
starter="$root/software/starter"
bsp_name=Zybo-Z7-20-Petalinux-2022-1.bsp
bsp_hash=864e150970dfad80b81cf2cb8115b80422d08e6760ed8d1e39fb717ce1087870
bsp_url="https://github.com/Digilent/Zybo-Z7/releases/download/20/Petalinux/2022.1-1/$bsp_name"
for tool in bootgen mkimage cpio mkfs.fat mcopy sfdisk curl flock; do
    command -v "$tool" >/dev/null || { echo "Missing $tool. Install the packages in the README." >&2; exit 1; }
done
mkdir -p "$out"
exec 9>"$out/.starter-build.lock"
flock 9
work="$(mktemp -d "$out/.starter.XXXXXX")"
trap 'rm -rf -- "$work"' EXIT
bsp="${RADAR_BSP:-$out/$bsp_name}"
verify_bsp() { printf '%s  %s\n' "$bsp_hash" "$1" | sha256sum -c --status; }
if [[ ! -f "$bsp" && -z "${RADAR_BSP:-}" ]]; then
    curl --fail --location --retry 2 --output "$work/vendor.bsp" "$bsp_url"
    verify_bsp "$work/vendor.bsp" || { echo 'Downloaded Digilent BSP failed its checksum.' >&2; exit 1; }
    mv "$work/vendor.bsp" "$bsp"
else
    verify_bsp "$bsp" || { echo "Missing or incorrect Digilent 2022.1 BSP: $bsp" >&2; exit 1; }
fi
(cd "$release" && sha256sum -c SHA256SUMS)
mkdir "$work/radar" "$work/vendor" "$work/card" "$work/rootfs"
tar -xzf "$release/radar-profile.tar.gz" -C "$work/radar"
(cd "$work/radar" && sha256sum -c SHA256SUMS)
if [[ "${1:-}" == --built ]]; then
    (cd "$out" && sha256sum -c bitstream.SHA256)
    cp "$out/system.bit" "$work/radar/system.bit"
fi
# Extract only named boot components. No vendor demo bitstream is used.
vendor=os/pre-built/linux/images
tar -xf "$bsp" -C "$work/vendor" --strip-components=4 \
    "$vendor/zynq_fsbl.elf" "$vendor/u-boot.elf" "$vendor/system.dtb" "$vendor/uImage" "$vendor/rootfs.tar.gz"
cd "$work"
cat > boot.bif <<'BIF'
the_ROM_image:
{
    [bootloader] vendor/zynq_fsbl.elf
    vendor/u-boot.elf
    [load=0x00100000] vendor/system.dtb
}
BIF
bootgen -arch zynq -image boot.bif -o card/BOOT.BIN
cp vendor/uImage card/uImage
cp radar/system.dtb card/radar.dtb
cp radar/system.bit card/system.bit
mkimage -A arm -O linux -T script -C none -n 'Acoustic radar' -d "$starter/boot.cmd" card/boot.scr
# The small RAM root contains the USB bridge, its runtime and the matching UIO module.
module=lib/modules/5.15.19-xilinx-v2022.1/kernel/drivers/uio/uio_pdrv_genirq.ko
tar -xzf vendor/rootfs.tar.gz -C rootfs --no-same-owner \
    ./bin/busybox.nosuid ./lib/ld-linux-armhf.so.3 ./lib/libc.so.6 ./lib/libm.so.6 "./$module"
mv rootfs/bin/busybox.nosuid rootfs/bin/busybox
mv "rootfs/$module" rootfs/lib/uio_pdrv_genirq.ko
mkdir -p rootfs/{dev,proc,sys,tmp,run,etc,var/run,opt/zybo/radar}
for applet in sh cat uname ls; do ln -s busybox "rootfs/bin/$applet"; done
install -m 0755 "$starter/init" rootfs/init
install -m 0755 "$starter/radar-login" rootfs/radar-login
install -m 0755 radar/radar-stream rootfs/opt/zybo/radar/radar-stream
(cd rootfs && find . -print0 | LC_ALL=C sort -z | cpio --null -o -H newc --owner=0:0 --quiet | gzip -n > ../rootfs.cpio.gz)
mkimage -A arm -O linux -T ramdisk -C gzip -n 'Acoustic radar USB console' -d rootfs.cpio.gz card/radar.ramdisk
# 1 MiB alignment followed by a bootable 64 MiB FAT32 partition.
truncate -s 64M boot.fat
mkfs.fat -F 32 -n RADAR boot.fat >/dev/null
mcopy -i boot.fat card/* ::/
truncate -s 65M radar-sd.img
printf 'label: dos\nunit: sectors\n\nstart=2048, size=131072, type=c, bootable\n' | sfdisk --no-reread radar-sd.img >/dev/null
dd if=boot.fat of=radar-sd.img bs=1M seek=1 conv=notrunc status=none
mv -fT radar-sd.img "$out/radar-sd.img"
echo "Ready: $out/radar-sd.img"
