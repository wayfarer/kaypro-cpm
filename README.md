# CP/M

Emulated CP/M machines you can drive interactively or from a script.

Underneath, the emulator is [RunCPM](https://github.com/MockbaTheBorg/RunCPM), a generic Z80 CP/M 2.2 machine. There's no machine-specific BIOS, terminal emulation, or disk geometry — each machine's identity lives in its software bundle and drive layout, not in the hardware. The one hardware concession is a modem (see below): a small local patch gives RunCPM a serial port at the Kaypros' historical modem ports.

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

## MACRO-80

Z80/8080 macro assembler. Source is `.MAC`; start it with `.Z80` and use `ASEG` / `ORG 100H` for a standalone `.COM`. The same L80 that links FORTRAN links its output.

```
A0> M80 B:PROG=B:PROG   assemble B:PROG.MAC -> B:PROG.REL (no listing)
A0> M80 =B:PROG         same, but also writes a B:PROG.PRN listing
A0> L80 B:PROG,B:PROG/N/E   link -> B:PROG.COM
A0> B:PROG              run
```

## SUBMIT

DRI's batch transient. Put one CP/M command per line in a `.SUB` file and the CCP runs them in order; while a batch is active the prompt terminator is `$` rather than `>`, and it returns to `>` when the batch ends. RunCPM's internal CCP processes the `$$$.SUB` mechanism natively.

```
A0> SUBMIT B:BUILD      run the commands in B:BUILD.SUB
```

A scripted session that only recognizes the `>` prompt still works: it simply waits until the whole batch has finished.

## The modem

The real Kaypro 10 had a built-in 300-baud modem (an RJ11 jack on the back, wired to Z80 SIO channel A). The emulated machines have one too, with TCP as the phone network:

- A patch to RunCPM (`harness/patches/`) puts a minimal SIO at the machine's historical modem ports — **data 04h, status 06h** on the Kaypros — bridged over a Unix socket to the session daemon.
- The daemon answers the other end as a Hayes-style smart modem (`harness/modem.py`). Real Kaypro modems predate the AT command set — bundled software dialed a TI chip directly — but AT is the dialect every terminal program and every human speaks, so that's what the modem presents.

A machine gets a modem by having a `modem.json` next to its drives (port map, listen port, phonebook). Both Kaypros have one. Anything that can poll the SIO can use it; from MBASIC:

```
Ok  A$="ATDT 127.0.0.1:2324"+CHR$(13)
Ok  FOR I=1 TO LEN(A$):OUT 4,ASC(MID$(A$,I,1)):NEXT   ' dial
Ok  IF (INP(6) AND 1)=1 THEN PRINT CHR$(INP(4));      ' read a reply byte
```

What works, in Hayes terms:

- `ATDT host:port` dials any TCP endpoint; `ATDT <number>` looks the number up in the machine's phonebook. `CONNECT` / `BUSY` / `NO CARRIER` result codes as you'd expect.
- Each machine listens for calls (kaypro-10 on port 2323, kaypro-2-84 on 2324): an inbound TCP connection rings the modem (`RING`), answered with `ATA` or auto-answered with `ATS0=1`.
- The machines can call each other — the phonebooks are pre-wired so kaypro-10 dials `2` to reach the Kaypro 2, which dials `10` to call back.
- `+++` (with guard time) escapes to command mode, `ATO` resumes, `ATH` hangs up; `ATE/Q/V`, S-registers, and the classic `AT&C1&D2`-style knobs are accepted.
- Dialing a telnet port (23, or a phonebook entry marked `"telnet": true`) transparently strips telnet option negotiation, so internet telnet BBSes look like a clean serial line.
- `"baud": 300` in `modem.json` paces delivery to an authentic ~30 chars/sec; the default (`0`) is full speed.

`python cpm.py status` shows the modem's state alongside the session. The daemon owns the modem, so scripted and interactive native sessions get it automatically; the Docker image runs bare RunCPM with the bridge dormant.

## Tests

```bash
make test
```

Boots every machine and drives it through a real FORTRAN compile, link and run — and, on machines with a modem, an AT dialogue and a dialed TCP round-trip driven from MBASIC. Needs `make native` first; skips cleanly without it. The modem engine's own tests (`tests/test_modem.py`) run against loopback sockets and need no binary.

## Adding a machine

Create `machines/<name>/` with drives (either `A/0/`, `B/0/` directories or drive-letter symlinks onto named stores), a `download_software.sh` to fetch its software, and a `README.md` telling its story. Add a `modem.json` if it should have a modem (pick an unused listen port). Then:

```bash
make MACHINE=<name> run
python cpm.py --machine <name> run "DIR"
```

No harness changes needed. `make machines` lists what's available.

## Known limitations

- A CP/M program that blocks waiting for input (e.g. BASIC's `INPUT`) will hang a scripted session until it times out. Use the interactive mode for those.
- The native harness is macOS-only. Docker works anywhere.
