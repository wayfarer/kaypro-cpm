#!/usr/bin/env python3
"""CLI for interacting with a running CP/M session.

Commands:
  cpm.py start              Start a background CP/M session
  cpm.py run <command>      Send a command and print output
  cpm.py write <filename> [user]   Write stdin to a file on B: drive
                            (user area 0 unless one is given;
                            --drive picks another drive letter)
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


# The daemon bounds each command at RUN_TIMEOUT seconds and always replies, so
# a silent socket past this margin means the daemon itself is gone.
REPLY_TIMEOUT = 330


def _send(sock: str, msg: dict) -> str:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(REPLY_TIMEOUT)
    try:
        client.connect(sock)
    except (FileNotFoundError, ConnectionRefusedError):
        client.close()
        raise SystemExit("No session running. Start one with: cpm.py start")
    try:
        client.send((json.dumps(msg) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
    except (socket.timeout, OSError):
        raise SystemExit(
            "Error: CP/M session is not responding; run `cpm.py stop` then "
            "`cpm.py start`."
        )
    finally:
        client.close()
    if not data.endswith(b"\n"):
        # An empty read means the daemon died mid-request; without this check
        # the recv loop above would spin forever on b"".
        raise SystemExit(
            "Error: CP/M session ended before replying; run `cpm.py stop` "
            "then `cpm.py start`."
        )
    return json.loads(data.decode())["output"]


def _daemon_alive(sock: str) -> bool:
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(2)
    try:
        probe.connect(sock)
        return True
    except OSError:
        return False
    finally:
        probe.close()


def cmd_start(name: str, machine_dir: str):
    sock = sock_path(machine_dir)
    if os.path.exists(sock):
        if _daemon_alive(sock):
            print(f"Session already running for {name}.")
            return
        # Stale files from a dead daemon; clear them and start fresh.
        for path in (sock, pid_path(machine_dir)):
            try:
                os.unlink(path)
            except OSError:
                pass
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
        pid_num = int(f.read().strip())
    try:
        os.kill(pid_num, signal.SIGTERM)
    except ProcessLookupError:
        pass
    # The daemon cleans these up on SIGTERM, but a dead daemon can't; unlink
    # so the next start doesn't see stale files.
    for path in (sock_path(machine_dir), pid):
        try:
            os.unlink(path)
        except OSError:
            pass
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
    write = sub.add_parser("write")
    write.add_argument("filename", help="file to create (content on stdin)")
    write.add_argument("user", nargs="?", type=int, default=0, help="user area 0-15 (default 0)")
    write.add_argument("--drive", default="B", help="drive letter A-P (default B)")

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
        sock = sock_path(machine_dir)
        running = os.path.exists(sock) and _daemon_alive(sock)
        print(f"{name}: {'running' if running else 'not running'}")
        if running and os.path.exists(os.path.join(machine_dir, "modem.json")):
            print(f"modem: {_send(sock_path(machine_dir), {'action': 'modem_status'})}")
    elif args.command == "run":
        print(_send(sock_path(machine_dir), {"action": "run", "command": args.cpm_command}))
    elif args.command == "write":
        print(_send(
            sock_path(machine_dir),
            {
                "action": "write",
                "filename": args.filename,
                "user": args.user,
                "drive": args.drive,
                "content": sys.stdin.read(),
            },
        ))


if __name__ == "__main__":
    main()
