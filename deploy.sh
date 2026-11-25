#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$root"
if [[ ! -s build/bitstream.SHA256 ]] || ! (cd build && sha256sum -c bitstream.SHA256); then
    printf 'Build the timing-checked bitstream with ./build.sh first.\n' >&2
    exit 1
fi
python="${PYTHON:-python3}"
upload="${ZYBO_UPLOADER:-$HOME/.codex/skills/zybo-file-transfer/scripts/upload.py}"
./scripts/build_board_software.sh
stage="$(mktemp -d "$root/build/.deployment.XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
cp build/system.bit build/board/{system.dtb,radar.scr,radar-stream} software/install.sh "$stage"
(cd "$stage" && sha256sum system.bit system.dtb radar.scr radar-stream install.sh > SHA256SUMS)
id="$(sha256sum build/system.bit | cut -c1-12)-$(date +%s)"
bundle="$root/build/acoustic-radar-$id.tar.gz"
tar -C "$stage" -czf "$bundle" SHA256SUMS system.bit system.dtb radar.scr radar-stream install.sh
destination="/root/${bundle##*/}"
"$python" "$upload" "$bundle" "$destination"
"$python" scripts/board.py install --bundle "$destination"
"$python" scripts/board.py boot
"$python" scripts/board.py self-test
