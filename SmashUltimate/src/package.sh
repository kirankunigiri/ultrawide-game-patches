#!/usr/bin/env bash
# Build the SmashUltimate release zip (src/out/, git-ignored).
#   ./package.sh                 # 2480x2248 (OPPO Find N6 inner screen)
#   ./package.sh 5120 1440       # any other screen
# The zip holds one Eden mod folder: <name>/exefs/13.0.2.pchtxt, plus INSTALL.md.
set -euo pipefail
cd "$(dirname "$0")"
W=${1:-2480}; H=${2:-2248}; VERSION=${VERSION:-1.0}
OUT=out; STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
python3 -I make_vertplus.py --width "$W" --height "$H" --out "$STAGE" >/dev/null
NAME=$(ls "$STAGE")
cp ../dist/INSTALL.md "$STAGE/"
mkdir -p "$OUT"
ZIP="$OUT/smashultimate-$(echo "$NAME" | tr 'A-Z' 'a-z')-v$VERSION.zip"
rm -f "$ZIP"
(cd "$STAGE" && zip -qrX "$OLDPWD/$ZIP" "$NAME" INSTALL.md)
echo "$ZIP"
shasum -a 256 "$ZIP"
