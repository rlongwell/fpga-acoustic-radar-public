#!/bin/sh
# Allow the Wi-Fi kernel whose module ABI was checked against these exact files.
set -eu
printf '%s\n' \
    '910befbc3bd1067e48280549e5492cd3e9a1ee6e891f485e3fd535424e65c0c9  /opt/zybo/fx/zybofx_bridge.ko' \
    '3f611ac1f4a9f34ebd85dcc34a3031db6f68117e73c1c474877f987351ea9412  /opt/zybo/chain4/zybofx_bridge.ko' |
    sha256sum -c -
for profile in fx chain4; do
    hook="/opt/zybo/$profile/start.sh"
    if grep -Fq '6.6.40-dfx-hash-wifi)' "$hook"; then continue; fi
    test "$(grep -c 'Audio module kernel mismatch' "$hook")" -eq 1
    test ! -e "$hook.pre-wifi"
    cp -p "$hook" "$hook.pre-wifi"
    new=$(mktemp "$hook.wifi.XXXXXX")
    sed '/Audio module kernel mismatch/c\    case "$(uname -r)" in 6.6.40-dfx-hash|6.6.40-dfx-hash-wifi) ;; *) echo "Audio module kernel mismatch" >\&2; return 1 ;; esac' "$hook" > "$new"
    sh -n "$new"
    chmod 0755 "$new"
    mv -f "$new" "$hook"
done
sync
