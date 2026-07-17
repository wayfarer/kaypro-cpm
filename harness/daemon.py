"""Background daemon that holds a RunCPM session and serves commands over a Unix socket.

Run as: python -m harness.daemon --machine <name>
"""
import argparse
import json
import os
import signal
import socket
import sys

from . import pid_path, resolve_machine, sock_path
from .session import CPMSession

# Upper bound for a single CP/M command. A program that has not returned to
# the prompt by then is treated as stuck and the session is replaced, so one
# runaway command can never wedge the daemon permanently.
RUN_TIMEOUT = 300


def handle(msg: dict, session: CPMSession, machine_dir: str) -> str:
    action = msg.get("action")

    if action == "run":
        return session.run(msg["command"], timeout=RUN_TIMEOUT) or "(no output)"

    if action == "write":
        name = os.path.basename(msg["filename"])
        user = int(msg.get("user", 0))
        if not 0 <= user <= 15:
            return f"Invalid user area: {user}"
        area = os.path.join(machine_dir, "B", str(user))
        os.makedirs(area, exist_ok=True)
        with open(os.path.join(area, name), "w", newline="\r\n") as f:
            f.write(msg["content"])
        return f"Written {name} to B: user {user}"

    return f"Unknown action: {action!r}"


def main():
    parser = argparse.ArgumentParser(description="RunCPM session daemon")
    parser.add_argument("--machine")
    args = parser.parse_args()

    _, machine_dir = resolve_machine(args.machine)
    sock, pid = sock_path(machine_dir), pid_path(machine_dir)

    with open(pid, "w") as f:
        f.write(str(os.getpid()))

    session = CPMSession(machine_dir)

    if os.path.exists(sock):
        os.unlink(sock)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock)
    server.listen(1)

    def shutdown(_sig, _frame):
        session.close()
        for path in (sock, pid):
            if os.path.exists(path):
                os.unlink(path)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)

    while True:
        conn, _ = server.accept()
        try:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            result = handle(json.loads(data.decode()), session, machine_dir)

        except (TimeoutError, RuntimeError) as exc:
            # A stuck or dead emulator must never take the daemon down with it:
            # a crashed daemon leaves a stale socket behind and every later
            # client hangs on it. Replace the session and keep serving.
            if isinstance(exc, TimeoutError):
                reason = f"command timed out after {RUN_TIMEOUT} seconds"
            else:
                reason = str(exc)
            result = (
                f"Error: {reason}; the CP/M session has been restarted "
                "(drive state reset to A0>)."
            )
            try:
                session.close()
            except OSError:
                pass
            try:
                session = CPMSession(machine_dir)
            except Exception as restart_exc:
                result = f"Error: {reason}; session restart failed: {restart_exc}"

        except Exception as exc:
            result = f"Error: {exc}"

        try:
            conn.send((json.dumps({"output": result}) + "\n").encode())
        except OSError:
            pass
        finally:
            conn.close()


if __name__ == "__main__":
    main()
