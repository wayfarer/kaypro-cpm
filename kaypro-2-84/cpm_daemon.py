"""Background daemon that holds a RunCPM session and serves commands over a Unix socket."""
import json
import os
import signal
import socket
import sys

from cpm_session import CPMSession, PROJECT_ROOT

SOCK_PATH = os.path.join(PROJECT_ROOT, ".cpm.sock")
PID_PATH = os.path.join(PROJECT_ROOT, ".cpm.pid")


def main():
    with open(PID_PATH, "w") as f:
        f.write(str(os.getpid()))

    session = CPMSession()

    if os.path.exists(SOCK_PATH):
        os.unlink(SOCK_PATH)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCK_PATH)
    server.listen(1)

    def shutdown(sig, frame):
        session.close()
        for path in (SOCK_PATH, PID_PATH):
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
            msg = json.loads(data.decode())

            if msg["action"] == "run":
                output = session.run(msg["command"])
                result = output or "(no output)"

            elif msg["action"] == "write":
                path = os.path.join(PROJECT_ROOT, "B", "0", msg["filename"])
                with open(path, "w", newline="\r\n") as f:
                    f.write(msg["content"])
                result = f"Written {msg['filename']} to B:"

            else:
                result = f"Unknown action: {msg['action']}"

            conn.send((json.dumps({"output": result}) + "\n").encode())
        finally:
            conn.close()


if __name__ == "__main__":
    main()
