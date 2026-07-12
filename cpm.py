#!/usr/bin/env python3
"""CLI for interacting with a running CP/M session.

Commands:
  cpm.py start              Start a background CP/M session
  cpm.py run <command>      Send a command and print output
  cpm.py write <filename>   Write stdin to a file on B: drive
  cpm.py stop               Stop the background session
  cpm.py status             Show whether a session is running
  cpm.py machines           List available machines

Pass --machine <name> to target a machine other than the default
(kaypro-2-84). $CPM_MACHINE works too. Each machine has its own session.
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time

from harness import REPO_ROOT, machine_names, pid_path, resolve_machine, sock_path


def _send(sock: str, msg: dict) -> str:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(sock)
    except (FileNotFoundError, ConnectionRefusedError):
        raise SystemExit("No session running. Start one with: cpm.py start")
    client.send((json.dumps(msg) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        data += client.recv(4096)
    client.close()
    return json.loads(data.decode())["output"]


def cmd_start(name: str, machine_dir: str):
    sock = sock_path(machine_dir)
    if os.path.exists(sock):
        print(f"Session already running for {name}.")
        return
    subprocess.Popen(
        [sys.executable, "-m", "harness.daemon", "--machine", name],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        if os.path.exists(sock):
            print(f"CP/M session started ({name}).")
            return
        time.sleep(0.1)
    raise SystemExit(f"Error: session for {name} failed to start.")


def cmd_stop(name: str, machine_dir: str):
    pid = pid_path(machine_dir)
    if not os.path.exists(pid):
        print(f"No session running for {name}.")
        return
    with open(pid) as f:
        os.kill(int(f.read().strip()), signal.SIGTERM)
    print(f"CP/M session stopped ({name}).")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--machine", help="machine name under machines/")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("machines")
    sub.add_parser("run").add_argument("cpm_command", help="command to send to CP/M")
    sub.add_parser("write").add_argument("filename", help="file to create on B: (content on stdin)")

    args = parser.parse_args()

    if args.command == "machines":
        print("\n".join(machine_names()))
        return

    name, machine_dir = resolve_machine(args.machine)

    if args.command == "start":
        cmd_start(name, machine_dir)
    elif args.command == "stop":
        cmd_stop(name, machine_dir)
    elif args.command == "status":
        running = os.path.exists(sock_path(machine_dir))
        print(f"{name}: {'running' if running else 'not running'}")
    elif args.command == "run":
        print(_send(sock_path(machine_dir), {"action": "run", "command": args.cpm_command}))
    elif args.command == "write":
        print(_send(
            sock_path(machine_dir),
            {"action": "write", "filename": args.filename, "content": sys.stdin.read()},
        ))


if __name__ == "__main__":
    main()
