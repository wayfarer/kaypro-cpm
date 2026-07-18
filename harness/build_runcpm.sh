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
# Local patches (serial/modem bridge). --check first so drift against a newly
# bumped RUNCPM_REF fails the build instead of silently producing a binary
# without the bridge. Keep in sync with the same step in harness/Dockerfile.
# Absolute paths: git -C changes directory before reading the patch file.
for p in "$(cd "$(dirname "$0")" && pwd)/patches/"*.patch; do
  git -C /tmp/RunCPM-mac apply --check "$p"
  git -C /tmp/RunCPM-mac apply "$p"
done
cd /tmp/RunCPM-mac/RunCPM
make macosx build
cp RunCPM "$DEST/RunCPM"
echo "Done: $DEST/RunCPM"
