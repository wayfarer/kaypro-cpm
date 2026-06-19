#!/bin/bash
# Downloads Microsoft CP/M software from deramp.com into A/0/.
# These files are copyrighted by Microsoft but circulate freely
# in the retrocomputing community.
set -e
BASE="https://deramp.com/downloads/microsoft/CPM%20Software"
DEST="$(cd "$(dirname "$0")/A/0" && pwd)"

echo "Downloading MBASIC and FORTRAN-80 to $DEST..."

curl -sS -o "$DEST/MBASIC.COM"  "$BASE/MBASIC5.COM"   && echo "  MBASIC.COM"
curl -sS -o "$DEST/F80.COM"     "$BASE/FORTRAN-80%20(F80%20v3.44)/F80.COM"  && echo "  F80.COM"
curl -sS -o "$DEST/L80.COM"     "$BASE/FORTRAN-80%20(F80%20v3.44)/L80.COM"  && echo "  L80.COM"
curl -sS -o "$DEST/FORLIB.REL"  "$BASE/FORTRAN-80%20(F80%20v3.44)/FORLIB.REL" && echo "  FORLIB.REL"
curl -sS -o "$DEST/LIB.COM"     "$BASE/FORTRAN-80%20(F80%20v3.44)/LIB.COM"  && echo "  LIB.COM"

echo "Done."
