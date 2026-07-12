import os
import pty
import re
import select
import subprocess
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RUNCPM = os.path.join(PROJECT_ROOT, "RunCPM")

_PROMPT = re.compile(r"[A-P][0-9]>|Ok")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class CPMSession:
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
        self._buf = ""
        self._read_until_prompt()

    def _read_until_prompt(self, timeout: int = 30) -> str:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("CP/M prompt not received")
            r, _, _ = select.select([self._fd], [], [], min(remaining, 0.1))
            if r:
                try:
                    self._buf += os.read(self._fd, 4096).decode("utf-8", errors="replace")
                except OSError:
                    break
            if _PROMPT.search(self._buf):
                out, self._buf = self._buf, ""
                return out

    def run(self, command: str) -> str:
        os.write(self._fd, (command + "\r\n").encode())
        raw = self._read_until_prompt()
        # Strip ANSI, normalize line endings
        raw = _ANSI.sub("", raw).replace("\r\n", "\n").replace("\r", "\n")
        # Drop echoed command (first line) and trailing prompt
        lines = raw.split("\n")
        content = "\n".join(lines[1:])
        content = _PROMPT.sub("", content).strip()
        return content

    def close(self):
        self._proc.terminate()
        try:
            os.close(self._fd)
        except OSError:
            pass
