#!/usr/bin/env python3
"""CLI for interacting with a running CP/M session.

Commands:
  cpm.py start              Start a background CP/M session
  cpm.py run <command>      Send a command and print output
  cpm.py write <filename>   Write stdin to a file on B: drive
  cpm.py stop               Stop the background session
  cpm.py status             Show whether a session is running
"""
import json
import os
import signal
import socket
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SOCK_PATH = os.path.join(PROJECT_ROOT, ".cpm.sock")
PID_PATH = os.path.join(PROJECT_ROOT, ".cpm.pid")


def _send(msg: dict) -> str:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCK_PATH)
    client.send((json.dumps(msg) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        data += client.recv(4096)
    client.close()
    return json.loads(data.decode())["output"]


def cmd_start():
    if os.path.exists(SOCK_PATH):
        print("Session already running.")
        return
    subprocess.Popen(
        [sys.executable, os.path.join(PROJECT_ROOT, "cpm_daemon.py")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        if os.path.exists(SOCK_PATH):
            print("CP/M session started.")
            return
        time.sleep(0.1)
    print("Error: session failed to start.", file=sys.stderr)
    sys.exit(1)


def cmd_run(command: str):
    print(_send({"action": "run", "command": command}))


def cmd_write(filename: str):
    content = sys.stdin.read()
    print(_send({"action": "write", "filename": filename, "content": content}))


def cmd_stop():
    if not os.path.exists(PID_PATH):
        print("No session running.")
        return
    with open(PID_PATH) as f:
        pid = int(f.read().strip())
    os.kill(pid, signal.SIGTERM)
    print("CP/M session stopped.")


def cmd_status():
    if os.path.exists(SOCK_PATH):
        print("Running.")
    else:
        print("Not running.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "start":
        cmd_start()
    elif cmd == "run":
        if len(sys.argv) < 3:
            print("Usage: cpm.py run <command>", file=sys.stderr)
            sys.exit(1)
        cmd_run(sys.argv[2])
    elif cmd == "write":
        if len(sys.argv) < 3:
            print("Usage: cpm.py write <filename>  (reads content from stdin)", file=sys.stderr)
            sys.exit(1)
        cmd_write(sys.argv[2])
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "status":
        cmd_status()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
