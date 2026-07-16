import os
import pty
import re
import select
import subprocess
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RUNCPM = os.path.join(PROJECT_ROOT, "RunCPM")

_PROMPT_TAIL = re.compile(r"[A-P][0-9]>\s*$")
_OK_TAIL = re.compile(r"(?:^|\n)Ok\s*$")
_PROMPT_LINE = re.compile(r"^(?:[A-P][0-9]>\s*|Ok\s*)$")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class CPMSession:
    """Drives a RunCPM process over a PTY.

    A command is considered finished when the console goes quiet and the
    accumulated output ends with a CP/M prompt (A0> through P9>) or MBASIC's
    Ok prompt. Matching the prompt only at the tail of the buffer, then
    waiting a short settle window for late output, keeps multi-line tool
    output such as F80 and L80 banners from being mistaken for completion.
    """

    def __init__(self):
        master_fd, slave_fd = pty.openpty()
        self._proc = subprocess.Popen(
            [RUNCPM],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=PROJECT_ROOT,
            close_fds=True,
        )
        os.close(slave_fd)
        self._fd = master_fd
        self._read_until_prompt()

    def _read_chunk(self, timeout):
        """Return bytes read, b'' on EOF, or None if nothing arrived in time."""
        r, _, _ = select.select([self._fd], [], [], timeout)
        if not r:
            return None
        try:
            return os.read(self._fd, 65536)
        except OSError:
            return b""

    def _read_until_prompt(self, timeout: int = 120, settle: float = 0.3) -> str:
        buf = b""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self._read_chunk(0.05)
            if chunk == b"":
                raise RuntimeError("CP/M session terminated unexpectedly")
            if chunk:
                buf += chunk
                continue
            text = _ANSI.sub("", buf.decode("utf-8", errors="replace"))
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            if _PROMPT_TAIL.search(text) or _OK_TAIL.search(text):
                late = self._read_chunk(settle)
                if late:
                    buf += late
                    continue
                return text
        raise TimeoutError("CP/M prompt not received")

    def run(self, command: str, timeout: int = 120) -> str:
        os.write(self._fd, (command + "\r").encode())
        text = self._read_until_prompt(timeout=timeout)
        lines = text.split("\n")
        if lines and command in lines[0]:
            lines = lines[1:]
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and _PROMPT_LINE.match(lines[-1]):
            lines.pop()
        return "\n".join(lines).strip()

    def close(self):
        self._proc.terminate()
        try:
            os.close(self._fd)
        except OSError:
            pass
