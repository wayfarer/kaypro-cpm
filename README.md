# CP/M

Emulated CP/M machines you can drive interactively or from a script.

The first (and so far only) machine is a **Kaypro 2 (1984)** — Z80, 64K, CP/M 2.2, two floppy drives — carrying Microsoft BASIC-80 v5, Microsoft FORTRAN-80 v3.44, Microsoft MACRO-80, Digital Research CBASIC 2 (v2.07), and DRI's SUBMIT batch transient. It's modelled after a real machine owned by a mathematics professor.

## A note on the model number

It's a Kaypro **2**, not a Kaypro **II**, and the difference is real rather than a typo:

| | |
|---|---|
| **Kaypro II** (1982) | The original. Shipped S-BASIC and the Perfect Software suite — Perfect Writer, Speller, Filer, Calc. |
| **Kaypro 2** (1984) | Shipped WordStar 3.3 with MailMerge, and Microsoft BASIC. |

Kaypro changed the bundle in 1984, and the Roman-vs-Arabic numeral is how the two machines are told apart (the same split distinguishes the Kaypro IV '83 from the Kaypro 4 '84). This machine has MBASIC, so it's the 1984 one — hence `machines/kaypro-2-84/`. Please don't "correct" it to `kaypro-ii`.

FORTRAN-80, MACRO-80 and CBASIC were never part of any Kaypro bundle. They're here because the professor's real machine had them, not because the model shipped with them.

Underneath, the emulator is [RunCPM](https://github.com/MockbaTheBorg/RunCPM), a generic Z80 CP/M 2.2 machine. There's no Kaypro-specific BIOS, terminal emulation, or disk geometry — the machine's identity lives in its software bundle and drive layout, not in the hardware.

## Layout

```
cpm.py             CLI
harness/           RunCPM plumbing — emulator, pty, socket. Machine-agnostic.
machines/
  kaypro-2-84/     drives (A/0, B/0) and the software that belongs on them
tests/
```

A machine is just a directory under `machines/`. Everything else is shared.

The numbered subdirectory under each drive letter is the CP/M **user area** (0–15): `A/0` is drive A user 0, `B/3` would be drive B user 3. RunCPM materializes an area the first time a file lands in it, so a machine that wants populated user areas just checks in the numbered directories — no harness changes.

## Setup

Fetch MBASIC, FORTRAN-80 and CBASIC onto the A: drive (once):

```bash
bash machines/kaypro-2-84/download_software.sh
```

These are Microsoft and Digital Research binaries, still copyrighted but freely circulated in the retrocomputing community. They aren't checked in.

## Use it interactively

```bash
make              # build the Docker image and drop into CP/M
make run-persist  # same, but B: is mounted from the host so your work survives
```

## Drive it from a script

Build the native binary once (macOS), then talk to a background session:

```bash
make native

python cpm.py start           # start a session
python cpm.py run "DIR"       # send a command, print its output
python cpm.py write FIBO.FOR  # write stdin to a file on B:
python cpm.py status
python cpm.py stop
```

`cpm.py` is stateless; a background daemon holds the live emulator and is reachable over a Unix socket. Each machine gets its own session, so they can run concurrently.

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

## Tests

```bash
make test
```

Boots every machine and drives it through a real FORTRAN compile, link and run. Needs `make native` first; skips cleanly without it.

## Adding a machine

Create `machines/<name>/` with `A/0/` and `B/0/` drives and a script to fetch its software, then:

```bash
make MACHINE=<name> run
python cpm.py --machine <name> run "DIR"
```

No harness changes needed. `make machines` lists what's available.

## Known limitations

- A CP/M program that blocks waiting for input (e.g. BASIC's `INPUT`) will hang a scripted session until it times out. Use the interactive mode for those.
- The native harness is macOS-only. Docker works anywhere.

## Wanted

**WordStar 3.3** — genuinely part of the Kaypro 2/84 bundle, alongside MailMerge. It belongs in `machines/kaypro-2-84/A/0/` as `WS.COM`, but it's harder to source than the Microsoft tools.
