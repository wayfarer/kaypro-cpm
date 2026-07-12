#!/bin/bash
set -e
DEST="$(cd "$(dirname "$0")" && pwd)"
rm -rf /tmp/RunCPM-mac
git clone --depth 1 https://github.com/MockbaTheBorg/RunCPM /tmp/RunCPM-mac
cd /tmp/RunCPM-mac/RunCPM
make macosx build
cp RunCPM "$DEST/RunCPM"
echo "Done: $DEST/RunCPM"
