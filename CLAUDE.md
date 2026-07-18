# CLAUDE.md

Guidance for Claude Code working in this repository. See README.md for what the project is, how to run it, and the CP/M workflows.

## Rules

- **Python orchestration scripts must use the standard library only.** No external packages, no pip installs. `pty`, `os`, `select`, `socket` and `subprocess` cover everything needed here.
- **The machine is a Kaypro 2 (1984), not a Kaypro II (1982).** They are different machines with different software bundles. Don't "fix" `kaypro-2-84` to `kaypro-ii`. README.md explains why.

## Architecture

```
cpm.py  ──(Unix socket)──  harness.daemon  ──(pty)──  RunCPM binary
  CLI                        background                 CP/M 2.2
                             process
```

`harness/` is machine-agnostic: nothing in it knows about a Kaypro. A machine is a directory under `machines/` holding drives (`A/0`, `B/0`) and its software. Drive letters may also be symlinks onto named stores — `kaypro-10` keeps real dirs `hd0/`, `hd1/`, `floppy/` and rewires `A`/`B`/`C` with its `set-boot-mode.sh` (committed default: hd boot). Adding a machine should never require touching `harness/`.

RunCPM is pinned to a fixed commit in `harness/build_runcpm.sh` and `harness/Dockerfile` (upstream has no tags). Both builds apply the local patches in `harness/patches/` (currently the serial/modem bridge) after checkout — `git apply --check` fails the build loudly if a patch no longer applies. Bump the SHA in both files together, re-verify (and if needed regenerate) the patches against the new commit, and only land it after `make test` passes.

A machine gets a modem by having a `modem.json` beside its drives. The daemon then starts a `ModemEngine` (`harness/modem.py` — Hayes AT state machine, TCP dial/listen) and tells the patched emulator where its SIO lives via `CPM_MODEM_SOCKET`/`CPM_SIO_*_PORT` env vars; the byte stream runs over `.cpm.modem.sock` in the machine dir. Without the config (or the env vars) everything is dormant and RunCPM behaves stock. The engine is machine-agnostic: port numbers, listen port, and phonebook all live in the machine's config.

`cpm.py` is stateless — each invocation opens a socket and sends one newline-terminated JSON message (`{"action": "run"|"write", ...}`). The daemon holds the single long-lived `CPMSession`. The socket and PID file live in the machine's own directory, so machines don't collide.

RunCPM resolves `A:`, `B:` … against its working directory, which is why `CPMSession` runs it with `cwd=machine_dir`.

## Talking to the emulator — hard-won details

These are easy to get wrong and were the source of a real bug (see commit 8834838):

- **Terminate commands with a bare `\r`, never `\r\n`.** The CR executes the command; a trailing LF is read as a *second, empty* command line, and the CCP answers it with an extra prompt. That prompt then lands at the head of the next command's output.
- **A prompt is only a prompt at the end of a quiet stream.** Prompt-shaped text can occur inside a program's own output — `PRINT "Ok computer"` in MBASIC is enough to fool a naive match. `CPMSession` requires a prompt at the end of the buffer *and* ~80ms of silence, since the CCP prints its prompt immediately before blocking on input.
- **CP/M user numbers run 0–15, not 0–9**, and SUBMIT ends the prompt with `$` rather than `>`.
- **RunCPM reprints its version banner on every warm boot**, i.e. after each `.COM` exits. It's emulator chrome, not CP/M output, and `CPMSession` filters it.
- Lines arrive as `\r\r\n` — RunCPM emits `\r\n` and the pty adds another CR.

If you change output handling, run `make test`. The smoke test asserts on exact program output precisely because this layer's failure mode is plausible-looking-but-wrong text.

## Gotchas

- FORTRAN source must be ALL CAPS, fixed-format (code from column 7, labels in 1–5). Hollerith constants count characters — `13HSMOKE TEST OK` must match the string length exactly, or you get a confusing syntax error.
- Downloaded `.COM`/`.REL` binaries are gitignored (copyrighted Microsoft/DRI software) — `A/0` on kaypro-2-84, `hd0/0` on kaypro-10 (which has its own machine-local `.gitignore`). If a machine's boot drive looks empty, run its `download_software.sh`.
