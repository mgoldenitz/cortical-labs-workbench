import os
import re

import numpy as np
import pytest

from workbench.canonical import canonicalize
from workbench.config import RunConfig
from workbench.layout import LayoutUnavailable, load_layout, validate_layout
from workbench.metrics import compute_all
from workbench.pipeline import child_env, unexpected_env
from workbench.report import render_report


def test_sdk_env_is_complete_and_explicit():
    env = RunConfig(seconds=2, seed=7, start_offset=100).sdk_env()
    assert env == {
        "CL_SDK_RANDOM_SEED": "7",
        "CL_SDK_REPLAY_START_OFFSET": "100",
        "CL_SDK_ACCELERATED_TIME": "0",
        "CL_SDK_VISUALISATION": "0",
        "CL_SDK_SAMPLE_MEAN": "170",
        "CL_SDK_SPIKE_PERCENTILE": "99.995",
        "CL_SDK_SPIKE_VISIBILITY": "0",
    }


def test_wall_clock_is_default_and_labels():
    cfg = RunConfig()
    assert cfg.timing_mode == "wall_clock" and cfg.data_label == "SYNTHETIC"
    assert cfg.window_frames == 125_000
    assert RunConfig(replay_path="x.h5").data_label == "REPLAYED"


@pytest.mark.parametrize("bad", [dict(seconds=0), dict(start_offset=-1)])
def test_invalid_config(bad):
    with pytest.raises(ValueError):
        RunConfig(**bad)


def test_child_env_drops_inherited_sdk_vars(monkeypatch):
    monkeypatch.setenv("CL_SDK_DATA_SOURCE", "evil:factory")
    monkeypatch.setenv("CL_SDK_RANDOM_SEED", "999")
    env = child_env(RunConfig(seed=1))
    assert "CL_SDK_DATA_SOURCE" not in env
    assert env["CL_SDK_RANDOM_SEED"] == "1"
    assert env["PATH"] == os.environ["PATH"]


def test_unexpected_env_detection():
    expected = {"CL_SDK_RANDOM_SEED": "1"}
    assert unexpected_env({"CL_SDK_RANDOM_SEED": "1"}, expected) == {}
    bad = unexpected_env({"CL_SDK_RANDOM_SEED": "2", "CL_SDK_DATA_SOURCE": "a:b"}, expected)
    assert set(bad) == {"CL_SDK_RANDOM_SEED", "CL_SDK_DATA_SOURCE"}
    assert unexpected_env({}, expected) == {"CL_SDK_RANDOM_SEED": "(missing)"}


def test_layout_from_private_module_is_valid():
    layout = load_layout()
    assert layout.channel_count == 64
    assert layout.ground_channels == (0, 7, 56, 63)
    assert layout.reference_channels == (4,)
    assert layout.source == "cl.analysis._metrics._mea_layout"


def test_validate_layout_rejects_bad_grids():
    with pytest.raises(LayoutUnavailable):
        validate_layout([[0, 1], [2]], [], [])
    with pytest.raises(LayoutUnavailable):
        validate_layout([[0, 1], [1, 3]], [], [])
    with pytest.raises(LayoutUnavailable):
        validate_layout([[0, 1], [2, 3]], [9], [])


def _fake_run(tmp_path, status="complete"):
    layout = load_layout()
    rng = np.random.default_rng(1)
    n = 25_000
    samples = rng.integers(-40, 40, size=(n, 64)).astype(np.int16)
    ts = np.sort(rng.integers(0, n, size=80))
    ch = rng.choice([c for c in range(64) if c not in layout.non_signal_channels], size=80)
    canon = canonicalize(samples, ts, ch, n)
    metrics = compute_all(canon.spike_ts, canon.spike_ch, n_frames=n, fps=25_000, channel_count=64,
                          excluded_channels=layout.non_signal_channels)
    manifest = {"run_id": "test-run", "status": status, "data_label": "SYNTHETIC",
                "data_label_note": "note", "config": RunConfig(seconds=1).to_dict(),
                "acquisition": {"window_start_frame": 0, "window_frames": n}, "sdk": {}, "code": {},
                "integrity": {"checks": [{"name": "x", "passed": status == "complete",
                                          "severity": "error", "detail": "d"}]}}
    out = tmp_path / "report.html"
    render_report(manifest, metrics, canon, layout, out)
    return out.read_text()


def test_report_is_self_contained_and_labelled(tmp_path):
    html = _fake_run(tmp_path)
    assert "SYNTHETIC DATA" in html and "not evidence about biological" in html
    assert "COMPLETE" in html
    srcs = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert srcs and all(s.startswith("data:image/png;base64,") for s in srcs)
    assert "<script" not in html and "@import" not in html and "url(" not in html


def test_report_flags_incomplete_runs(tmp_path):
    html = _fake_run(tmp_path, status="incomplete")
    assert "INCOMPLETE" in html and "do not use these results" in html


def test_report_without_data_for_failed_runs(tmp_path):
    manifest = {"run_id": "f", "status": "failed", "data_label": "SYNTHETIC", "data_label_note": "n",
                "error": "worker exited with code 1", "config": {}, "acquisition": {}}
    render_report(manifest, None, None, None, tmp_path / "r.html")
    html = (tmp_path / "r.html").read_text()
    assert "FAILED" in html and "worker exited with code 1" in html
