#!/bin/bash
# Select which boot mode the emulated Kaypro 10 presents by rewiring the
# A/B/C drive-letter symlinks onto the real stores (hd0, hd1, floppy).
#
#   set-boot-mode.sh          print the current mode
#   set-boot-mode.sh hd       A->hd0  B->hd1  C->floppy  (committed default)
#   set-boot-mode.sh floppy   A->floppy  B->hd0  C->hd1
#
# The underlying disks are shared between modes, just like the real machine:
# same stores, different letters. Takes effect on the next session start.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

current() {
  case "$(readlink "$DIR/A")" in
    hd0)    echo hd ;;
    floppy) echo floppy ;;
    *)      echo unknown ;;
  esac
}

if [ $# -eq 0 ]; then
  echo "Boot mode: $(current)"
  exit 0
fi

MODE="$1"
if [ "$MODE" != hd ] && [ "$MODE" != floppy ]; then
  echo "Usage: $(basename "$0") [hd|floppy]" >&2
  exit 1
fi

if [ -e "$DIR/.cpm.sock" ] || [ -e "$DIR/.cpm.pid" ]; then
  echo "Session running for kaypro-10 — stop it first (python cpm.py --machine kaypro-10 stop)" >&2
  exit 1
fi

if [ "$MODE" = hd ]; then
  ln -sfn hd0    "$DIR/A"
  ln -sfn hd1    "$DIR/B"
  ln -sfn floppy "$DIR/C"
else
  ln -sfn floppy "$DIR/A"
  ln -sfn hd0    "$DIR/B"
  ln -sfn hd1    "$DIR/C"
fi

echo "Boot mode: $MODE (takes effect on next session start)"
if [ "$MODE" != hd ]; then
  echo "Note: hd is the committed default — flip back before committing."
fi
