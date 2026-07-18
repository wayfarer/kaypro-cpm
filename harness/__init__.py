"""Shared RunCPM harness.

Nothing in here is machine-specific. A "machine" is just a directory under
machines/ holding the drives (A/0, B/0) and whatever software belongs on them;
this package supplies the emulator, the pty plumbing, and the socket protocol.
"""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MACHINES_DIR = os.path.join(REPO_ROOT, "machines")
RUNCPM = os.path.join(REPO_ROOT, "RunCPM")

DEFAULT_MACHINE = "kaypro-2-84"


def machine_names() -> list:
    if not os.path.isdir(MACHINES_DIR):
        return []
    return sorted(
        name
        for name in os.listdir(MACHINES_DIR)
        if os.path.isdir(os.path.join(MACHINES_DIR, name)) and not name.startswith(".")
    )


def resolve_machine(name: str = None) -> tuple:
    """Return (name, directory) for a machine. Precedence: argument, $CPM_MACHINE, default."""
    name = name or os.environ.get("CPM_MACHINE") or DEFAULT_MACHINE
    path = os.path.join(MACHINES_DIR, name)
    if not os.path.isdir(path):
        available = ", ".join(machine_names()) or "none"
        raise SystemExit(f"Unknown machine {name!r}. Available: {available}")
    return name, path


# Kept beside the drives, so two machines can run at once without colliding.
def sock_path(machine_dir: str) -> str:
    return os.path.join(machine_dir, ".cpm.sock")


def pid_path(machine_dir: str) -> str:
    return os.path.join(machine_dir, ".cpm.pid")


def modem_sock_path(machine_dir: str) -> str:
    return os.path.join(machine_dir, ".cpm.modem.sock")
