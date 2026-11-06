"""Process cleanup by run marker (Linux /proc only)."""

import os
import subprocess
import sys
import time

import pytest

from workbench import procs

pytestmark = pytest.mark.skipif(not procs.supported(), reason="process cleanup needs Linux /proc")

# A parent that starts a grandchild in a new session (as cl-sdk's simulator does), prints
# the grandchild's PID, then sleeps. Killing the parent does not reach the grandchild.
TREE = r"""
import subprocess, sys, time, signal
if len(sys.argv) > 1:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen([sys.executable, "-c",
    "import signal, sys, time\n"
    "if len(sys.argv) > 1: signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "time.sleep(120)", *sys.argv[1:]], start_new_session=True)
print(child.pid, flush=True)
time.sleep(120)
"""


def _start_tree(marker, *args):
    env = {**os.environ, procs.RUN_MARKER_ENV: marker}
    parent = subprocess.Popen([sys.executable, "-c", TREE, *args], env=env, stdout=subprocess.PIPE, text=True)
    grandchild = int(parent.stdout.readline())
    return parent, grandchild


def _gone(pid):
    return not procs._alive(pid)


def test_finds_and_stops_a_tree_that_escaped_the_process_group():
    marker = f"test-{os.getpid()}-{time.time_ns()}"
    parent, grandchild = _start_tree(marker)
    try:
        assert os.getpgid(grandchild) != os.getpgid(parent.pid)
        assert set(procs.find_marked(marker)) == {parent.pid, grandchild}
        rec = procs.stop_marked(marker, grace_s=5)
        assert rec["supported"] is True
        assert set(rec["found"]) == {parent.pid, grandchild}
        assert set(rec["terminated"]) == {parent.pid, grandchild}
        assert rec["killed"] == [] and rec["remaining"] == []
        parent.wait(timeout=5)
        assert _gone(grandchild)
        assert procs.find_marked(marker) == []
    finally:
        for pid in (parent.pid, grandchild):
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass


def test_processes_that_ignore_sigterm_are_killed_within_the_bound():
    marker = f"test-{os.getpid()}-{time.time_ns()}"
    parent, grandchild = _start_tree(marker, "ignore-term")
    try:
        t0 = time.monotonic()
        rec = procs.stop_marked(marker, grace_s=1, kill_wait_s=2)
        assert time.monotonic() - t0 < 1 + 2 + 1
        assert set(rec["killed"]) == {parent.pid, grandchild}
        assert rec["remaining"] == []
        parent.wait(timeout=5)
        assert _gone(grandchild)
    finally:
        for pid in (parent.pid, grandchild):
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass


def test_other_markers_are_left_alone():
    mine, other = f"a-{time.time_ns()}", f"b-{time.time_ns()}"
    parent, grandchild = _start_tree(other)
    try:
        assert procs.stop_marked(mine)["found"] == []
        assert procs._alive(parent.pid) and procs._alive(grandchild)
    finally:
        procs.stop_marked(other, grace_s=2)
        parent.wait(timeout=5)


def test_unsupported_platform_claims_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(procs, "PROC", tmp_path / "no-proc")
    rec = procs.stop_marked("anything")
    assert rec["supported"] is False and rec["found"] == [] and "Linux" in rec["note"]
