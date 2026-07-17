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


def handle(msg: dict, session: CPMSession, machine_dir: str) -> str:
    action = msg.get("action")

    if action == "run":
        return session.run(msg["command"]) or "(no output)"

    if action == "write":
        name = os.path.basename(msg["filename"])
        user = int(msg.get("user", 0))
        if not 0 <= user <= 15:
            return f"Invalid user area: {user}"
        drive = str(msg.get("drive", "B")).upper()
        if drive not in "ABCDEFGHIJKLMNOP" or len(drive) != 1:
            return f"Invalid drive: {drive}"
        area = os.path.join(machine_dir, drive, str(user))
        os.makedirs(area, exist_ok=True)
        with open(os.path.join(area, name), "w", newline="\r\n") as f:
            f.write(msg["content"])
        return f"Written {name} to {drive}: user {user}"

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
                data += conn.recv(4096)
            result = handle(json.loads(data.decode()), session, machine_dir)
            conn.send((json.dumps({"output": result}) + "\n").encode())
        finally:
            conn.close()


if __name__ == "__main__":
    main()
