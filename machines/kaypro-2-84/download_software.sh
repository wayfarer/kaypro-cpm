#!/bin/bash
# Downloads CP/M software into A/0/: Microsoft tools from deramp.com, and
# CBASIC 2 and DRI SUBMIT from retroarchive.org. These files are copyrighted
# (Microsoft / Digital Research) but circulate freely in the retrocomputing
# community.
set -e
BASE="https://deramp.com/downloads/microsoft/CPM%20Software"
DEST="$(cd "$(dirname "$0")/A/0" && pwd)"

echo "Downloading MBASIC, FORTRAN-80 and MACRO-80 to $DEST..."

curl -sS -o "$DEST/MBASIC.COM"  "$BASE/MBASIC5.COM"   && echo "  MBASIC.COM"
curl -sS -o "$DEST/F80.COM"     "$BASE/FORTRAN-80%20(F80%20v3.44)/F80.COM"  && echo "  F80.COM"
curl -sS -o "$DEST/L80.COM"     "$BASE/FORTRAN-80%20(F80%20v3.44)/L80.COM"  && echo "  L80.COM"
curl -sS -o "$DEST/FORLIB.REL"  "$BASE/FORTRAN-80%20(F80%20v3.44)/FORLIB.REL" && echo "  FORLIB.REL"
curl -sS -o "$DEST/LIB.COM"     "$BASE/FORTRAN-80%20(F80%20v3.44)/LIB.COM"  && echo "  LIB.COM"
# The M80.COM at the top level of the deramp CP/M tree does not run under
# RunCPM (it warm-boots instantly and assembles nothing). The copy on the
# COBOL-80 disk is a working MACRO-80 build, so fetch that one; L80 above
# links its .REL output as-is.
curl -sS -o "$DEST/M80.COM"     "$BASE/COBOL-80/M80.COM" && echo "  M80.COM"

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

echo "Downloading SUBMIT to $DEST..."

# DRI's SUBMIT.COM batch transient, from the standard CP/M 2.2 distribution.
# RunCPM's internal CCP processes the $$$.SUB file natively, so SUBMIT
# batches chain to completion; the CCP prompt ends with '$' instead of '>'
# while one is running.
curl -sS -o "$TMP/STDCPM22.ZIP" "http://www.retroarchive.org/cpm/os/STDCPM22.ZIP"
unzip -q -o "$TMP/STDCPM22.ZIP" SUBMIT.COM -d "$TMP"
cp "$TMP/SUBMIT.COM" "$DEST/SUBMIT.COM" && echo "  SUBMIT.COM"

echo "Done."
