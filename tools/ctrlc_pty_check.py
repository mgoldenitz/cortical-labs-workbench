"""Press Ctrl-C during acquisition of `workbench run` in a pseudo-terminal, then check what is left.

Linux only. `workbench run` is started as the foreground job of a new pseudo-terminal. Once
the simulator's data producer is running, the script writes 0x03 (Ctrl-C) to the terminal;
the terminal line discipline turns it into SIGINT for the foreground process group, as a
real terminal does. The simulator's helper processes are in other sessions, so they do not
receive it.

It then reports how long `workbench run` took to exit, which processes with the run's
marker were alive before Ctrl-C and are alive afterwards, the recorded status, the files
kept, and the exit code of `workbench verify`. It exits non-zero if the exit took longer
than --limit seconds, a marked process remains, or verify returned 0.

    python tools/ctrlc_pty_check.py --out /tmp/ctrlc-check [--delay 2] [--seconds 30]
"""

from __future__ import annotations

import argparse
import json
import os
import pty
import select
import subprocess
import sys
import termios
import time
from pathlib import Path

from workbench import procs


def _cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        return "(gone)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output folder for the run (created; should be empty)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds to wait after the data producer starts")
    ap.add_argument("--seconds", type=float, default=30.0, help="recording window, longer than the test")
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--limit", type=float, default=15.0, help="maximum seconds from Ctrl-C to exit")
    args = ap.parse_args()
    if not procs.supported():
        print("not supported: this check needs Linux /proc")
        return 2

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    workbench = Path(sys.executable).parent / "workbench"
    argv = [str(workbench), "run", "--seconds", str(args.seconds), "--seed", str(args.seed), "--out", str(out)]

    pid, fd = pty.fork()
    if pid == 0:  # child: session leader with the pseudo-terminal as its controlling terminal
        os.execv(argv[0], argv)

    attrs = termios.tcgetattr(fd)
    assert attrs[3] & termios.ISIG and attrs[6][termios.VINTR] == b"\x03", "terminal does not map Ctrl-C to SIGINT"
    output = bytearray()

    def drain(seconds: float) -> bool:
        """Read terminal output for up to `seconds`; False once the terminal has closed."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    return False
                if not chunk:
                    return False
                output.extend(chunk)
        return True

    started = time.monotonic()
    run_dir = None
    while time.monotonic() - started < 60:
        drain(0.2)
        dirs = [p for p in out.iterdir() if p.is_dir()]
        if dirs and (dirs[0] / "manifest.json").exists():
            run_dir = dirs[0]
            if any("cl-data-producer" in _cmdline(p) for p in procs.find_marked(run_dir.name)):
                break
    else:
        os.kill(pid, 9)
        print("acquisition did not start within 60 s")
        return 1
    drain(args.delay)

    run_id = run_dir.name
    foreground = os.tcgetpgrp(fd)
    before = [{"pid": p, "in_foreground_group": os.getpgid(p) == foreground, "cmd": _cmdline(p)[:100]}
              for p in procs.find_marked(run_id)]
    status_before = json.loads((run_dir / "manifest.json").read_text()).get("status")

    t_ctrl_c = time.monotonic()
    os.write(fd, b"\x03")
    status = None
    while True:
        open_ = drain(0.1)
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        if not open_:
            _, status = os.waitpid(pid, 0)
            break
        if time.monotonic() - t_ctrl_c > 60:
            os.kill(pid, 9)
            _, status = os.waitpid(pid, 0)
            break
    exit_s = time.monotonic() - t_ctrl_c
    after = procs.find_marked(run_id)
    time.sleep(2)
    after_2s = procs.find_marked(run_id)

    manifest = json.loads((run_dir / "manifest.json").read_text())
    verify = subprocess.run([str(workbench), "verify", str(run_dir)], capture_output=True, text=True)
    report = {
        "run_id": run_id,
        "seconds_after_producer_start": args.delay,
        "marked_before_ctrl_c": before,
        "status_before_ctrl_c": status_before,
        "exit_seconds_after_ctrl_c": round(exit_s, 2),
        "workbench_exit_code": os.waitstatus_to_exitcode(status),
        "marked_after_exit": after,
        "marked_2s_after_exit": after_2s,
        "status": manifest.get("status"),
        "error": manifest.get("error"),
        "files_kept": sorted(p.name for p in run_dir.iterdir()),
        "verify_exit_code": verify.returncode,
        "verify_output": verify.stdout.strip().splitlines(),
    }
    print(json.dumps(report, indent=2))
    ok = exit_s <= args.limit and not after and not after_2s and verify.returncode != 0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
