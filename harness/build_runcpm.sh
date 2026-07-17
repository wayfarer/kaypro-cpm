#!/bin/bash
set -e
# Upstream has no release tags, so we pin by commit SHA. Keep in sync with
# ARG RUNCPM_REF in harness/Dockerfile.
RUNCPM_REF="${RUNCPM_REF:-1c19a8baa073ecf746d6501cc28239d139b809d7}"
# The binary is shared by every machine, so it lives at the repo root.
DEST="$(cd "$(dirname "$0")/.." && pwd)"
rm -rf /tmp/RunCPM-mac
# A shallow clone can't check out an arbitrary SHA; fetch the pinned commit directly.
git init -q /tmp/RunCPM-mac
git -C /tmp/RunCPM-mac remote add origin https://github.com/MockbaTheBorg/RunCPM
git -C /tmp/RunCPM-mac fetch -q --depth 1 origin "$RUNCPM_REF"
git -C /tmp/RunCPM-mac checkout -q FETCH_HEAD
cd /tmp/RunCPM-mac/RunCPM
make macosx build
cp RunCPM "$DEST/RunCPM"
echo "Done: $DEST/RunCPM"
