"""Integration tests: these start the cl-sdk simulator in child processes.

All data here is synthetic (random source) or replayed from a synthetic recording.
"""

import json
import shutil

import numpy as np
import pytest

from workbench import cli
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


def test_runs_complete_with_expected_outputs(runs):
    _, made = runs
    for name, (run_dir, m) in made.items():
        assert m["status"] == "complete", (name, m.get("integrity"), m.get("error"))
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
