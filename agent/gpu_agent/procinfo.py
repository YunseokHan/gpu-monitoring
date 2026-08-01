"""Best-effort ``/proc`` lookups to put a human name and owner on a GPU process.

None of this is guaranteed to work: NVML reports host PIDs, and on a node where the
agent runs inside a container those PIDs may not resolve. Every helper therefore
degrades to whatever NVML itself told us rather than raising.
"""

from __future__ import annotations

import os
import pwd

# argv[0] of a dummy worker. The agent starts it with this exact argv[0] so that
# nvidia-smi, /proc and our own dashboard all agree on the name.
DUMMY_ARGV0 = "dummy"

_MAX_CMDLINE = 160


def read_cmdline(pid: int) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def read_comm(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/comm") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def read_username(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("Uid:"):
                    uid = int(line.split()[1])
                    try:
                        return pwd.getpwuid(uid).pw_name
                    except KeyError:
                        return str(uid)
    except OSError:
        pass
    return ""


def describe(pid: int, nvml_name: str = "") -> tuple[str, str, str]:
    """Return ``(name, cmdline, user)`` for a GPU process.

    ``name`` is the short thing shown in the dashboard, ``cmdline`` the fuller context
    (which conda env, which script) shown underneath it.
    """
    argv = read_cmdline(pid)
    if argv:
        name = os.path.basename(argv[0]) or argv[0]
        cmdline = " ".join(argv)
    else:
        # No /proc access: fall back to the path NVML gave us.
        name = os.path.basename(nvml_name) if nvml_name else (read_comm(pid) or "?")
        cmdline = nvml_name

    # A bare "python" tells nobody anything; borrow the script name when there is one.
    if name in ("python", "python3", "python3.10", "python3.11", "python3.12", "python3.13"):
        for arg in argv[1:]:
            if arg.endswith(".py"):
                name = f"{name} {os.path.basename(arg)}"
                break

    if len(cmdline) > _MAX_CMDLINE:
        cmdline = cmdline[: _MAX_CMDLINE - 1] + "…"

    return name, cmdline, read_username(pid)


def is_dummy_process(name: str, cmdline: str, nvml_name: str) -> bool:
    """Is this one of our dummy workers?

    Matching on argv[0] rather than on a PID we remember keeps this correct across agent
    restarts, and inside containers where NVML reports a PID we cannot map back.
    """
    for candidate in (name, cmdline.split(" ")[0] if cmdline else "", nvml_name):
        if candidate and os.path.basename(candidate) == DUMMY_ARGV0:
            return True
    return False
