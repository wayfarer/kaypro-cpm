#!/bin/bash
# Downloads CP/M software into A/0/: Microsoft tools from deramp.com and
# CBASIC 2 from retroarchive.org. These files are copyrighted (Microsoft /
# Digital Research) but circulate freely in the retrocomputing community.
set -e
BASE="https://deramp.com/downloads/microsoft/CPM%20Software"
DEST="$(cd "$(dirname "$0")/A/0" && pwd)"

echo "Downloading MBASIC and FORTRAN-80 to $DEST..."

curl -sS -o "$DEST/MBASIC.COM"  "$BASE/MBASIC5.COM"   && echo "  MBASIC.COM"
curl -sS -o "$DEST/F80.COM"     "$BASE/FORTRAN-80%20(F80%20v3.44)/F80.COM"  && echo "  F80.COM"
curl -sS -o "$DEST/L80.COM"     "$BASE/FORTRAN-80%20(F80%20v3.44)/L80.COM"  && echo "  L80.COM"
curl -sS -o "$DEST/FORLIB.REL"  "$BASE/FORTRAN-80%20(F80%20v3.44)/FORLIB.REL" && echo "  FORLIB.REL"
curl -sS -o "$DEST/LIB.COM"     "$BASE/FORTRAN-80%20(F80%20v3.44)/LIB.COM"  && echo "  LIB.COM"

echo "Downloading CBASIC 2 to $DEST..."

# retroarchive's CB80.ZIP carries the whole DRI CBASIC family. We take the
# CBASIC 2 P-code pair: CBASE2.COM is the compiler (banner: "CBASIC COMPILER
# VER 2.07"), installed under its canonical manual name CBAS2.COM; CRUN2.COM
# is the matching runtime that executes the compiler's .INT output.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -sS -o "$TMP/CB80.ZIP" "http://www.retroarchive.org/cpm/lang/CB80.ZIP"
unzip -q -o "$TMP/CB80.ZIP" CBASE2.COM CRUN2.COM -d "$TMP"
cp "$TMP/CBASE2.COM" "$DEST/CBAS2.COM" && echo "  CBAS2.COM"
cp "$TMP/CRUN2.COM"  "$DEST/CRUN2.COM" && echo "  CRUN2.COM"

echo "Done."
