# Kaypro 10

Z80, 64K, CP/M 2.2 — one physical floppy drive and a 10 MB hard disk split into two 5 MB partitions. The hard disk is what set the Kaypro 10 apart from its two-floppy siblings.

## Boot modes and drive letters

CP/M leaned hard on the idea of "drive A" and "drive B", so the real machine shifted its drive letters depending on how it was booted:

| Boot mode | A: | B: | C: |
|---|---|---|---|
| **Hard drive** (default) | HD partition 1 (`hd0`) | HD partition 2 (`hd1`) | floppy |
| **Floppy** | floppy | HD partition 1 (`hd0`) | HD partition 2 (`hd1`) |

This machine models that with three real stores — `hd0/`, `hd1/`, `floppy/` — and `A`, `B`, `C` as symlinks that a script rewires:

```bash
bash machines/kaypro-10/set-boot-mode.sh          # print the current mode
bash machines/kaypro-10/set-boot-mode.sh floppy   # switch to floppy boot
bash machines/kaypro-10/set-boot-mode.sh hd       # back to hard-drive boot
```

The underlying disks are shared between modes, exactly like the real hardware: a file written in one boot mode is there in the other, just under a different letter. The script refuses to flip while a session is running (stop it first); a flip takes effect on the next session start. **Hard-drive boot is the committed default** — don't commit a flipped tree.

## Software

The bundle (MBASIC, FORTRAN-80, CBASIC — same tools as the Kaypro 2) lives on `hd0/0`, the hard-disk boot partition, which is where a real Kaypro 10 kept its system and tools. Fetch it once:

```bash
bash machines/kaypro-10/download_software.sh
```

## Testing note

`make test` exercises whichever mode the symlinks currently point at, and the language checks assume the committed hard-drive boot default (tools on A:). Under floppy boot, A: is the blank floppy, so those checks don't apply unless you stage tools onto it.
