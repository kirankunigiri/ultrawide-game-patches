#!/usr/bin/env bash
# Build the SmashUltimate release zip (src/out/, git-ignored).
#   ./package.sh                        # 2480x2248 (OPPO Find N6 inner screen)
#   ./package.sh --width 5120 --height 1440
#   ./package.sh --aspect 20:9          # any make_vertplus.py screen option works
#   ./package.sh --from-adb             # the connected phone's current screen
# The zip holds one Eden mod folder: <name>/exefs/13.0.2.pchtxt, plus INSTALL.md.
set -euo pipefail
cd "$(dirname "$0")"
VERSION=${VERSION:-1.0}
OUT=out; STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
python3 -I make_vertplus.py "$@" --out "$STAGE" >/dev/null
NAME=$(ls "$STAGE")
cp ../dist/INSTALL.md "$STAGE/"
mkdir -p "$OUT"
ZIP="$OUT/smashultimate-$(echo "$NAME" | tr 'A-Z' 'a-z')-v$VERSION.zip"
rm -f "$ZIP"
(cd "$STAGE" && zip -qrX "$OLDPWD/$ZIP" "$NAME" INSTALL.md)
echo "$ZIP"
shasum -a 256 "$ZIP"
