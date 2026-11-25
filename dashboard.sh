#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python="${PYTHON:-python3}"
"$python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Python 3.10 or newer is required")'
cd "$root"
exec 9>"$root/.bootstrap.lock"
flock 9
if [[ ! -x .venv/bin/python ]]; then
    "$python" -m venv .venv
fi
signature="$(sha256sum requirements.txt)"
if [[ ! -f .venv/dependency-signature || "$(cat .venv/dependency-signature)" != "$signature" ]]; then
    .venv/bin/python -m pip install -r requirements.txt
    printf '%s\n' "$signature" > .venv/dependency-signature
fi
flock -u 9
exec 9>&-
exec .venv/bin/python -m radar.gui "$@"
