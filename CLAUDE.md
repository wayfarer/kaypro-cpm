# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# CP/M

A Kaypro CP/M 2.2 emulator (Z80, two floppy drives) pre-loaded with Microsoft BASIC-80 v5 and FORTRAN-80 v3.44 — modelled after a real machine owned by a mathematics professor.

**Rule:** Python orchestration scripts must use the standard library only. No external packages.

---

## Two modes of operation

### First-time setup

```bash
bash download_software.sh   # fetch MBASIC and FORTRAN-80 into A/0/
```

### 1. Interactive (Docker)

```bash
make          # builds image and drops into CP/M (default target)
make run-persist  # same, with B: drive mounted from host
```

### 2. Harness / programmatic (native binary, macOS only)

```bash
make native   # builds ./RunCPM via build_runcpm.sh (one-time)
```

Then drive it via the CLI:

```bash
python cpm.py start           # start background CP/M session
python cpm.py status          # check if running
python cpm.py run "DIR"       # send a command, print output
python cpm.py write FIBO.FOR  # write stdin to B: drive
python cpm.py stop            # stop the session
```

---

## Architecture (harness mode)

```
cpm.py  ──(Unix socket)──  cpm_daemon.py  ──(pty)──  RunCPM binary
  CLI                         background                  CP/M 2.2
                              process
```

`cpm.py` is stateless — each invocation opens a socket connection to the daemon and sends a newline-terminated JSON message `{"action": "run"|"write", ...}`. The daemon holds the single long-lived `CPMSession` (in `cpm_session.py`) which drives RunCPM via a PTY using `pty`, `os`, and `select`. The socket file is `.cpm.sock` and the daemon PID is tracked in `.cpm.pid`, both in the project root.

`cpm_session.py` reads from the PTY until a CP/M prompt (`A0>`, `B0>`, etc.) or MBASIC's `Ok` prompt appears, then returns the output with the echo and prompt stripped.

---

## Drive layout

```
A/0/         ← system disk (read-only in practice)
  MBASIC.COM   Microsoft BASIC-80 v5
  F80.COM      Microsoft FORTRAN-80 v3.44 compiler
  L80.COM      Microsoft Link-80 v3.44 linker
  FORLIB.REL   FORTRAN-80 runtime library
  LIB.COM      Library manager
  HELLO.BAS    Sample BASIC program

B/0/         ← work disk (source files, compiled output)
```

`A/` and `B/` on the host map directly to CP/M drives inside both the Docker container and the native session. Files written to `B/0/` on the host appear immediately on B: in a running native session.

---

## FORTRAN-80 workflow

```
A0> F80 =B:PROG                           compile B:PROG.FOR → B:PROG.REL
A0> L80 B:PROG,A:FORLIB/S,B:PROG/N/E     link → B:PROG.COM
A0> B:PROG                                run
```

FORTRAN source must be ALL CAPS, fixed-format (code starts column 7, labels columns 1–5).

## BASIC workflow

```
A0> MBASIC                 enter interpreter (Ok prompt)
Ok  LOAD "B:PROG.BAS"
Ok  RUN
Ok  SYSTEM                 return to CP/M
```

---

## Future scope

- **WordStar 3.3** — likely on the original Kaypro disk. `WS.COM` in `A/0/`. Harder to source than the Microsoft tools.
