"""Integration tests: these start the cl-sdk simulator in child processes.

All data here is synthetic (random source) or replayed from a synthetic recording.
"""

import json
import shutil

import numpy as np
import pytest

from workbench import cli, procs
from workbench.config import RunConfig
from workbench.pipeline import finalize, run
from workbench.recording_io import load_recording

pytestmark = pytest.mark.sdk


@pytest.fixture(scope="session")
def runs(tmp_path_factory):
    out = tmp_path_factory.mktemp("runs")
    made = {}
    made["acc_a"] = run(RunConfig(seconds=1, seed=42, accelerated=True), out)
    made["acc_b"] = run(RunConfig(seconds=1, seed=42, accelerated=True), out)
    made["wall"] = run(RunConfig(seconds=1, seed=42, accelerated=False), out)
    made["seed7"] = run(RunConfig(seconds=1, seed=7, accelerated=True), out)
    return out, made


def _why(name, run_dir, m):
    """Enough context to diagnose a run that did not complete, from the assertion message alone."""
    failed = [c for c in (m.get("integrity") or {}).get("checks", []) if not c["passed"]]
    log = run_dir / "worker.log"
    tail = log.read_text(errors="replace")[-2000:] if log.exists() else "(no worker.log)"
    return (f"{name}: status={m.get('status')!r} error={m.get('error')!r} run_dir={run_dir}\n"
            f"failed checks: {json.dumps(failed, indent=1, default=str)}\n"
            f"worker: {json.dumps(m['acquisition'].get('worker'), default=str)[:2000]}\n"
            f"worker.log tail:\n{tail}")


def test_runs_complete_with_expected_outputs(runs):
    _, made = runs
    for name, (run_dir, m) in made.items():
        assert m["status"] == "complete", _why(name, run_dir, m)
        for f in ("recording.h5", "manifest.json", "metrics.json", "channel_metrics.csv", "report.html",
                  "worker.log", "worker_result.json", "config.json"):
            assert (run_dir / f).exists(), (name, f)
        assert m["data_label"] == "SYNTHETIC"
        assert m["sdk"]["cl_sdk_version"] == "1.0.0"
        assert m["sdk"]["private_modules_used"] == ["cl.analysis._metrics._mea_layout"]
        assert m["acquisition"]["recording_attributes"]["file_format"]["version"] == "SDK"
        assert m["acquisition"]["recording_attributes"]["start_timestamp"] == 0
        assert m["acquisition"]["worker"]["is_simulator"] is True


def test_unique_run_ids(runs):
    _, made = runs
    ids = [m["run_id"] for _, m in made.values()]
    assert len(set(ids)) == len(ids)


def test_same_seed_same_canonical_data_and_metrics(runs):
    _, made = runs
    a, b, w = (made[k][1] for k in ("acc_a", "acc_b", "wall"))
    for other in (b, w):  # includes wall-clock vs accelerated
        assert other["canonical"] == a["canonical"]
        assert other["metrics_sha256"] == a["metrics_sha256"]
    assert cli.main(["compare", str(made["acc_a"][0]), str(made["wall"][0])]) == 0


def test_whole_files_differ_but_canonical_data_does_not(runs):
    _, made = runs
    fa = made["acc_a"][1]["files"]["recording.h5"]["sha256"]
    fb = made["acc_b"][1]["files"]["recording.h5"]["sha256"]
    # The HDF5 files carry creation times and run IDs, so they are not byte-identical;
    # this is why runs are compared on canonical data.
    assert fa != fb


def test_different_seed_changes_sample_data(runs):
    _, made = runs
    a, s7 = made["acc_a"][1], made["seed7"][1]
    assert a["canonical"]["samples_sha256"] != s7["canonical"]["samples_sha256"]
    assert cli.main(["compare", str(made["acc_a"][0]), str(made["seed7"][0])]) == 1


def test_verify_detects_tampering(runs, tmp_path):
    _, made = runs
    src = made["acc_a"][0]
    assert cli.main(["verify", str(src)]) == 0
    copy = tmp_path / "copy"
    shutil.copytree(src, copy)
    m = json.loads((copy / "metrics.json").read_text())
    m["summary"]["total_spikes"] += 1
    (copy / "metrics.json").write_text(json.dumps(m))
    assert cli.main(["verify", str(copy)]) == 1


def test_overrun_in_log_marks_run_incomplete_and_keeps_files(runs, tmp_path):
    _, made = runs
    src_dir, src_manifest = made["acc_a"]
    work = tmp_path / "overrun"
    shutil.copytree(src_dir, work)
    manifest = json.loads((work / "manifest.json").read_text())
    log = "Recording fell behind ring buffer (cursor=0, buf_start=118928). Some data was lost."
    m = finalize(work, manifest, worker_log=log, env_unexpected={}, cfg=RunConfig(seconds=1, seed=42))
    assert m["status"] == "incomplete"
    assert "no_ring_buffer_overrun" in m["integrity"]["errors"]
    assert (work / "recording.h5").exists()
    assert "INCOMPLETE" in (work / "report.html").read_text()
    assert json.loads((work / "metrics.json").read_text())["status"] == "incomplete"
    assert cli.main(["verify", str(work)]) == 2  # consistent with its manifest, but not complete


def test_replay_reproduces_source_frames(runs):
    out, made = runs
    src = made["acc_a"][0] / "recording.h5"
    run_dir, m = run(RunConfig(seconds=0.5, seed=42, accelerated=True, replay_path=str(src)), out)
    assert m["status"] == "complete", m.get("integrity")
    assert m["data_label"] == "REPLAYED"
    assert m["acquisition"]["replay_source"]["sha256"] == made["acc_a"][1]["files"]["recording.h5"]["sha256"]
    a, b = load_recording(src), load_recording(run_dir / "recording.h5")
    n = 12_500
    assert np.array_equal(a.samples[:n], b.samples[:n])


def test_failed_run_is_kept_and_marked(runs, tmp_path):
    out, _ = runs
    bogus = tmp_path / "not_hdf5.h5"
    bogus.write_text("this is not an HDF5 file")
    run_dir, m = run(RunConfig(seconds=0.2, seed=1, accelerated=True, replay_path=str(bogus)), out,
                     timeout_s=60)
    assert m["status"] == "failed"
    assert m["error"]
    assert (run_dir / "manifest.json").exists() and (run_dir / "worker.log").exists()
    assert "FAILED" in (run_dir / "report.html").read_text()
    assert cli.main(["verify", str(run_dir)]) == 2


@pytest.mark.skipif(not procs.supported(), reason="process cleanup is implemented for Linux /proc only")
def test_timeout_stops_worker_and_simulator_processes(tmp_path):
    # A 30 s window with a 6 s timeout: the worker is still recording when it is stopped.
    # Before the fix, cl-sdk's data producer (started in its own session) outlived the worker.
    run_dir, m = run(RunConfig(seconds=30, seed=3, accelerated=False), tmp_path, timeout_s=6)
    assert m["status"] == "failed"
    assert "timed out" in m["error"]
    worker = m["acquisition"]["worker"]
    assert worker["timed_out"] is True and worker["returncode"] is None
    cleanup = worker["process_cleanup"]
    assert cleanup["supported"] is True
    assert cleanup["found"], "expected the worker and simulator processes to be found by marker"
    assert cleanup["remaining"] == []
    assert procs.find_marked(m["run_id"]) == []
    for f in ("manifest.json", "config.json", "worker.log", "report.html"):
        assert (run_dir / f).exists(), f
    assert cli.main(["verify", str(run_dir)]) == 2


@pytest.mark.parametrize("name", ["acc_a", "wall"])
def test_analysis_uses_exact_window(runs, name):
    """Recordings overshoot the window by a few frames; analysis must use exactly [0, N)."""
    from workbench.canonical import canonicalize, samples_digest, spikes_digest
    from workbench.metrics import compute_all
    from workbench.layout import load_layout

    run_dir, m = runs[1][name]
    n = m["config"]["window_frames"]
    rec = load_recording(run_dir / "recording.h5")
    assert rec.samples.shape[0] > n  # the overshoot exists (N+1 accelerated, N+5 wall clock so far)
    assert m["canonical"]["window_frames"] == n

    # Recompute independently from the raw file, slicing by hand.
    window = np.ascontiguousarray(rec.samples[:n])
    keep = rec.spike_ts < n
    c = canonicalize(window, rec.spike_ts[keep], rec.spike_ch[keep], n)
    assert samples_digest(c) == m["canonical"]["samples_sha256"]
    assert spikes_digest(c) == m["canonical"]["spikes_sha256"]
    assert m["canonical"]["n_spikes"] == int(keep.sum())

    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics["summary"]["n_frames"] == n
    layout = load_layout()
    again = compute_all(c.spike_ts, c.spike_ch, n_frames=n, fps=25_000, channel_count=64,
                        excluded_channels=layout.non_signal_channels)
    assert again["summary"] == metrics["summary"]
    assert again["channels"] == metrics["channels"]


def test_cli_run_with_default_relative_out_dir(tmp_path, monkeypatch):
    # `workbench run` defaults to --out runs, a relative path; the worker runs with
    # cwd=run_dir, so this checks the paths handed to it still resolve.
    monkeypatch.chdir(tmp_path)
    assert cli.main(["run", "--seconds", "1", "--seed", "42"]) == 0
    (run_dir,) = (tmp_path / "runs").iterdir()
    m = json.loads((run_dir / "manifest.json").read_text())
    assert m["status"] == "complete", (m.get("error"), m.get("integrity"))
    assert (run_dir / "recording.h5").exists()
    assert cli.main(["verify", str(run_dir.relative_to(tmp_path))]) == 0


@pytest.mark.skipif(not procs.supported(), reason="process cleanup is implemented for Linux /proc only")
def test_interrupt_records_process_cleanup_in_manifest(tmp_path):
    # Ctrl-C in a terminal sends SIGINT to the foreground process group: the parent and the
    # worker, but not the simulator's helpers, which run in their own sessions. Reproduce that
    # by starting the parent in a new process group and signalling the whole group.
    import os
    import signal
    import subprocess
    import sys
    import time
    from pathlib import Path

    out = tmp_path / "runs"
    code = ("import sys; from pathlib import Path; from workbench.config import RunConfig; "
            "from workbench.pipeline import run; run(RunConfig(seconds=30, seed=3), Path(sys.argv[1]))")
    parent = subprocess.Popen([sys.executable, "-c", code, str(out)], start_new_session=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 60
        run_dir = None
        while time.monotonic() < deadline:
            dirs = list(out.glob("*/manifest.json")) if out.exists() else []
            if dirs:
                run_dir = dirs[0].parent
                cmds = [Path(f"/proc/{p}/cmdline").read_bytes() for p in procs.find_marked(run_dir.name)
                        if Path(f"/proc/{p}/cmdline").exists()]
                if any(b"cl-data-producer" in c for c in cmds):
                    break
            time.sleep(0.1)
        else:
            pytest.fail("acquisition did not start within 60 s")
        time.sleep(1)
        os.killpg(parent.pid, signal.SIGINT)
        output = parent.communicate(timeout=30)[0].decode(errors="replace")
    finally:
        if parent.poll() is None:
            os.killpg(parent.pid, signal.SIGKILL)
            parent.wait()

    assert parent.returncode != 0 and "KeyboardInterrupt" in output, output[-2000:]  # interrupt propagated
    m = json.loads((run_dir / "manifest.json").read_text())
    assert m["status"] == "failed"
    assert m["error"] == "interrupted by user"
    cleanup = m["acquisition"]["worker"]["process_cleanup"]
    assert cleanup["supported"] is True
    assert set(cleanup) >= {"found", "terminated", "killed", "remaining"}, cleanup
    # "found" may be empty: SIGINT reaches the worker too, and it can exit, with the simulator's
    # helpers, before the scan runs. What must hold is that nothing is left.
    assert cleanup["remaining"] == []
    assert procs.find_marked(m["run_id"]) == []
    assert cli.main(["verify", str(run_dir)]) != 0
