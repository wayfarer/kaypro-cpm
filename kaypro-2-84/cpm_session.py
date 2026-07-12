import os
import pty
import re
import select
import subprocess
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RUNCPM = os.path.join(PROJECT_ROOT, "RunCPM")

# The CCP builds its prompt as "\r\n<drive><user><term>" and then blocks for
# input. User numbers run 0-15, and the terminator is '$' while a SUBMIT file
# is running.
_CPM_PROMPT = r"[A-P](?:1[0-5]|[0-9])[>$]"
_PROMPT_AT_END = re.compile(rf"(?:{_CPM_PROMPT}|^Ok)[ \t\r\n]*\Z", re.MULTILINE)

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# RunCPM reprints this on every warm boot, i.e. after each .COM exits. It is
# emulator chrome, not CP/M output — a real Kaypro just returns to the prompt.
_BANNER = re.compile(r"^RunCPM Version .*$", re.MULTILINE)


class SessionClosed(RuntimeError):
    """The RunCPM process went away."""


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

    def _read_until_prompt(self, timeout: float = 30.0, settle: float = 0.08) -> str:
        """Read until the emulator is idle at a prompt.

        A prompt-shaped string can occur inside a program's own output, so
        matching one is not by itself proof that the command has finished. We
        also require that no bytes have arrived for `settle` seconds: the CCP
        prints its prompt immediately before blocking on input, so a prompt at
        the end of a stream that has gone quiet means it really is our turn.
        """
        deadline = time.monotonic() + timeout
        last_data = time.monotonic()
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(f"no CP/M prompt within {timeout}s")

            readable, _, _ = select.select([self._fd], [], [], 0.02)
            if readable:
                try:
                    chunk = os.read(self._fd, 4096)
                except OSError as exc:
                    raise SessionClosed("RunCPM closed the terminal") from exc
                if not chunk:
                    raise SessionClosed("RunCPM exited")
                self._buf += chunk.decode("utf-8", errors="replace")
                last_data = time.monotonic()
                continue

            if (
                time.monotonic() - last_data >= settle
                and _PROMPT_AT_END.search(self._buf)
            ):
                out, self._buf = self._buf, ""
                return out

    def run(self, command: str) -> str:
        # Terminate with a bare CR. A trailing LF is taken as a second, empty
        # command line, which the CCP answers with an extra prompt; that prompt
        # then lands at the head of the next command's output.
        os.write(self._fd, (command + "\r").encode())
        return self._clean(self._read_until_prompt(), command)

    @staticmethod
    def _clean(raw: str, command: str) -> str:
        # RunCPM emits \r\n and the pty adds another CR, so lines arrive as \r\r\n.
        text = _ANSI.sub("", raw).replace("\r", "")
        text = _PROMPT_AT_END.sub("", text)
        text = _BANNER.sub("", text)

        lines = text.split("\n")
        if lines and lines[0].strip() == command.strip():
            lines = lines[1:]
        return "\n".join(lines).strip()

    def close(self):
        self._proc.terminate()
        try:
            os.close(self._fd)
        except OSError:
            pass
