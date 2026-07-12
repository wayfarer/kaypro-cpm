# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# CP/M

A collection of emulated CP/M machines, one per directory. Each machine directory is self-contained: its own drives, Dockerfile, Makefile, and Python harness.

```
kaypro-2-84/   ← Kaypro 2 (1984). CP/M 2.2, Z80, two floppies.
```

**Rule:** Python orchestration scripts must use the standard library only. No external packages.

The root `Makefile` forwards every target to a machine directory, defaulting to `kaypro-2-84`:

```bash
make                      # same as: make -C kaypro-2-84 run
make MACHINE=some-other-machine run
```

All commands below can equally be run from inside the machine directory.

---

## Machines

### `kaypro-2-84` — Kaypro 2 (1984)

Z80, 64K, CP/M 2.2, two single-sided 191K floppies. Pre-loaded with Microsoft BASIC-80 v5 and FORTRAN-80 v3.44 — modelled after a real machine owned by a mathematics professor.

Note the model naming, which is easy to get wrong: the **Kaypro II** (Roman numeral, 1982) shipped S-BASIC and the Perfect Software suite. The **Kaypro 2** (Arabic, 1984) is a different machine, and is the one that shipped MBASIC and WordStar 3.3 — which is why this directory is `kaypro-2-84`. The same Roman/Arabic split distinguishes the Kaypro IV '83 from the Kaypro 4 '84.

The emulator underneath is [RunCPM](https://github.com/MockbaTheBorg/RunCPM), a generic Z80 CP/M 2.2 machine. There is no Kaypro-specific BIOS, terminal emulation, or disk geometry — the Kaypro identity is in the software bundle and the drive layout, not the hardware.

---

## Two modes of operation

### First-time setup

```bash
bash kaypro-2-84/download_software.sh   # fetch MBASIC and FORTRAN-80 into kaypro-2-84/A/0/
```

### 1. Interactive (Docker)

```bash
make              # builds image and drops into CP/M (default target)
make run-persist  # same, with B: drive mounted from host
```

### 2. Harness / programmatic (native binary, macOS only)

```bash
make native   # builds kaypro-2-84/RunCPM via build_runcpm.sh (one-time)
```

Then drive it via the CLI, from inside the machine directory:

```bash
cd kaypro-2-84
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

`cpm.py` is stateless — each invocation opens a socket connection to the daemon and sends a newline-terminated JSON message `{"action": "run"|"write", ...}`. The daemon holds the single long-lived `CPMSession` (in `cpm_session.py`) which drives RunCPM via a PTY using `pty`, `os`, and `select`.

All three scripts resolve their paths from `__file__`, so the machine directory is the root for everything: the socket is `kaypro-2-84/.cpm.sock`, the daemon PID `kaypro-2-84/.cpm.pid`, and the drives `kaypro-2-84/A/`, `kaypro-2-84/B/`. Each machine directory therefore gets its own independent session.

`cpm_session.py` reads from the PTY until a CP/M prompt (`A0>`, `B0>`, etc.) or MBASIC's `Ok` prompt appears, then returns the output with the echo and prompt stripped.

---

## Drive layout

Relative to the machine directory:

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

FORTRAN-80 was never part of any Kaypro bundle — a professor would have bought it separately. It is here because the real machine had it, not because the model shipped with it.

## BASIC workflow

```
A0> MBASIC                 enter interpreter (Ok prompt)
Ok  LOAD "B:PROG.BAS"
Ok  RUN
Ok  SYSTEM                 return to CP/M
```

---

## Future scope

- **WordStar 3.3** — part of the genuine Kaypro 2/84 bundle (with MailMerge), so it belongs in `kaypro-2-84/A/0/` as `WS.COM`. Harder to source than the Microsoft tools.
