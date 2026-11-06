"""Find and stop the processes one run started (Linux only).

The cl-sdk simulator starts its own helper processes in new sessions
(`start_new_session=True` in cl._sim._subprocess), so killing the worker or its
process group does not reach them, and once the worker dies they are re-parented
and can no longer be found by walking parent ids. Every process of a run instead
inherits one environment variable, RUN_MARKER_ENV, set to the run id; this module
finds live processes by that marker in /proc/<pid>/environ.

Only Linux has been tested. On a system without /proc (macOS, Windows) the scan
finds nothing and the result says so; no cleanup is claimed there.
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

RUN_MARKER_ENV = "CL_WORKBENCH_RUN_MARKER"
PROC = Path("/proc")


def supported() -> bool:
    return PROC.is_dir() and (PROC / "self" / "environ").exists()


def _alive(pid: int) -> bool:
    try:
        state = (PROC / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return False
    return state != "Z"  # a zombie has exited; only its parent can reap it


def find_marked(marker: str) -> list[int]:
    """PIDs of live processes whose environment has RUN_MARKER_ENV=marker (this process excluded)."""
    if not supported():
        return []
    needle = f"{RUN_MARKER_ENV}={marker}".encode()
    me = os.getpid()
    found = []
    for entry in PROC.iterdir():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        try:
            env = (entry / "environ").read_bytes()
        except OSError:  # gone, or not ours
            continue
        if needle in env.split(b"\0") and _alive(int(entry.name)):
            found.append(int(entry.name))
    return sorted(found)


def _wait_gone(marker: str, seconds: float) -> list[int]:
    left = find_marked(marker)
    deadline = time.monotonic() + seconds
    while left and time.monotonic() < deadline:
        time.sleep(0.1)
        left = find_marked(marker)  # also catches a process started after the first scan
    return left


def _signal(pids: list[int], sig: int) -> list[int]:
    sent = []
    for pid in pids:
        try:
            os.kill(pid, sig)
            sent.append(pid)
        except ProcessLookupError:
            pass
    return sent


def stop_marked(marker: str, settle_s: float = 0.0, grace_s: float = 5.0, kill_wait_s: float = 2.0) -> dict:
    """Make sure no process of this run is left alive; bounded by settle_s + grace_s + kill_wait_s.

    1. Wait up to settle_s for marked processes to exit on their own (after a normal worker exit
       the simulator's helpers may still be shutting down cleanly).
    2. SIGTERM whatever is left and wait up to grace_s.
    3. SIGKILL whatever is still left and wait up to kill_wait_s.

    Returns a record for the manifest; "remaining" should be empty.
    """
    if not supported():
        return {"supported": False, "found": [], "terminated": [], "killed": [], "remaining": [],
                "note": "process cleanup is implemented for Linux /proc only; nothing was checked"}
    found = find_marked(marker)
    left = _wait_gone(marker, settle_s) if settle_s else found
    terminated = _signal(left, signal.SIGTERM)
    left = _wait_gone(marker, grace_s) if terminated else left
    killed = _signal(left, signal.SIGKILL)
    remaining = _wait_gone(marker, kill_wait_s) if killed else left
    return {"supported": True, "found": found, "terminated": terminated, "killed": killed,
            "remaining": remaining}
