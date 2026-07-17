# CP/M

Emulated CP/M machines you can drive interactively or from a script.

Underneath, the emulator is [RunCPM](https://github.com/MockbaTheBorg/RunCPM), a generic Z80 CP/M 2.2 machine. There's no machine-specific BIOS, terminal emulation, or disk geometry — each machine's identity lives in its software bundle and drive layout, not in the hardware.

## Machines

| Machine | Description |
|---|---|
| [kaypro-2-84](machines/kaypro-2-84/README.md) | Kaypro 2 (1984) — two floppy drives; MBASIC, FORTRAN-80, CBASIC. The default machine. |
| [kaypro-10](machines/kaypro-10/README.md) | Kaypro 10 — one floppy plus a 10 MB hard disk in two partitions; selectable boot mode. |

## Layout

```
cpm.py             CLI
harness/           RunCPM plumbing — emulator, pty, socket. Machine-agnostic.
machines/
  kaypro-2-84/     drives (A/0, B/0) and the software that belongs on them
  kaypro-10/       real stores (hd0, hd1, floppy) with A/B/C symlinked per boot mode
tests/
```

A machine is just a directory under `machines/`, with its own `README.md`. Everything else is shared. A drive letter may be a plain directory (`A/`, `B/`) or a symlink onto a named store — RunCPM resolves letters against the machine directory either way.

The numbered subdirectory under each drive letter is the CP/M **user area** (0–15): `A/0` is drive A user 0, `B/3` would be drive B user 3. RunCPM materializes an area the first time a file lands in it, so a machine that wants populated user areas just checks in the numbered directories — no harness changes.

## Setup

Each machine fetches its own software (once):

```bash
bash machines/<name>/download_software.sh
```

The bundles are Microsoft and Digital Research binaries, still copyrighted but freely circulated in the retrocomputing community. They aren't checked in.

## Use it interactively

```bash
make              # build the Docker image and drop into CP/M (default machine)
make run-persist  # same, but B: is mounted from the host so your work survives

make MACHINE=kaypro-10 run   # any other machine
```

## Drive it from a script

Build the native binary once (macOS), then talk to a background session:

```bash
make native

python cpm.py start           # start a session
python cpm.py run "DIR"       # send a command, print its output
python cpm.py write FIBO.FOR  # write stdin to a file on B:
python cpm.py write --drive C DATA.TXT   # ...or any other drive
python cpm.py status
python cpm.py stop
```

`cpm.py` is stateless; a background daemon holds the live emulator and is reachable over a Unix socket. Pass `--machine <name>` (or set `$CPM_MACHINE`) to target a machine other than the default. Each machine gets its own session, so they can run concurrently.

## FORTRAN-80

Source must be ALL CAPS and fixed-format — code starts in column 7, labels in columns 1–5.

```
A0> F80 =B:PROG                        compile B:PROG.FOR -> B:PROG.REL
A0> L80 B:PROG,A:FORLIB/S,B:PROG/N/E   link -> B:PROG.COM
A0> B:PROG                             run
```

## BASIC

```
A0> MBASIC              enter the interpreter (Ok prompt)
Ok  LOAD "B:PROG.BAS"
Ok  RUN
Ok  SYSTEM              back to CP/M
```

## CBASIC

CBASIC 2 is a compiler/runtime pair: `CBAS2` compiles source to P-code (`.INT`), `CRUN2` executes it. Arithmetic is 14-digit BCD.

```
A0> CBAS2 B:PROG        compile B:PROG.BAS -> B:PROG.INT
A0> CRUN2 B:PROG        run
```

## Tests

```bash
make test
```

Boots every machine and drives it through a real FORTRAN compile, link and run. Needs `make native` first; skips cleanly without it.

## Adding a machine

Create `machines/<name>/` with drives (either `A/0/`, `B/0/` directories or drive-letter symlinks onto named stores), a `download_software.sh` to fetch its software, and a `README.md` telling its story. Then:

```bash
make MACHINE=<name> run
python cpm.py --machine <name> run "DIR"
```

No harness changes needed. `make machines` lists what's available.

## Known limitations

- A CP/M program that blocks waiting for input (e.g. BASIC's `INPUT`) will hang a scripted session until it times out. Use the interactive mode for those.
- The native harness is macOS-only. Docker works anywhere.
