import math

import numpy as np
import pytest

from workbench.metrics import MetricsConfig, channel_metrics, compare_metrics, compute_all, population_rate

FPS = 1000  # 1 frame = 1 ms keeps the expected values readable


def _spikes():
    # channel 1: regular 100 ms intervals; channel 2: intervals 100, 200 ms;
    # channel 3: one spike; channel 0: "excluded" channel with one spike.
    data = [(1, 0), (1, 100), (1, 200), (1, 300), (2, 0), (2, 100), (2, 300), (3, 500), (0, 50)]
    ch = np.array([c for c, _ in data])
    ts = np.array([t for _, t in data])
    return ts, ch


def test_channel_metrics_known_values():
    ts, ch = _spikes()
    rows = channel_metrics(ts, ch, n_frames=1000, fps=FPS, channel_count=5, excluded_channels=(0,))
    by = {r["channel"]: r for r in rows}
    assert by[1]["spike_count"] == 4 and by[1]["rate_hz"] == 4.0
    assert by[1]["isi_mean_ms"] == 100.0 and by[1]["isi_cv"] == 0.0
    assert by[2]["isi_mean_ms"] == 150.0
    assert by[2]["isi_cv"] == pytest.approx(50.0 / 150.0)
    assert by[3]["spike_count"] == 1 and by[3]["isi_mean_ms"] is None and by[3]["isi_cv"] is None
    assert by[4]["spike_count"] == 0 and by[4]["rate_hz"] == 0.0 and not by[4]["active"]
    assert by[0]["excluded"] and not by[0]["active"]


def test_isi_cv_needs_three_spikes():
    rows = channel_metrics(np.array([0, 10]), np.array([0, 0]), n_frames=100, fps=FPS, channel_count=1)
    assert rows[0]["isi_mean_ms"] == 10.0 and rows[0]["isi_cv"] is None


def test_summary_leaves_out_excluded_channels():
    ts, ch = _spikes()
    m = compute_all(ts, ch, n_frames=1000, fps=FPS, channel_count=5, excluded_channels=(0,),
                    config=MetricsConfig(population_bin_ms=250))
    s = m["summary"]
    assert s["channels_included"] == 4 and s["channels_excluded"] == [0]
    assert s["total_spikes"] == 8  # the spike on channel 0 is not counted
    assert s["active_channels"] == 3  # channels 1, 2, 3 (channel 4 has no spikes)
    assert s["mean_rate_hz"] == pytest.approx((4 + 3 + 1 + 0) / 4)
    # 250 ms bins over included channels: [0,250) has 5 spikes, [250,500) 2, [500,750) 1, [750,1000) 0
    assert s["population_rate_n_bins"] == 4
    assert s["population_rate_max_hz"] == pytest.approx(5 / 0.25)


def test_population_rate_drops_partial_bin_and_out_of_range():
    starts, counts = population_rate(np.array([0, 5, 99, 100, 250, -1, 400]), n_frames=260, fps=FPS, bin_ms=100)
    assert counts.tolist() == [3, 1]  # [0,100) and [100,200); 250 is in the dropped partial bin
    assert starts.tolist() == [0.0, 0.1]


@pytest.mark.parametrize("kwargs", [dict(n_frames=0, fps=1000), dict(n_frames=10, fps=0)])
def test_invalid_window_rejected(kwargs):
    with pytest.raises(ValueError):
        channel_metrics(np.array([]), np.array([]), channel_count=1, **kwargs)


def test_mismatched_spike_arrays_rejected():
    with pytest.raises(ValueError):
        channel_metrics(np.array([1, 2]), np.array([0]), n_frames=10, fps=FPS, channel_count=1)


def test_no_spikes_gives_zeros_not_nan():
    m = compute_all(np.array([], int), np.array([], int), n_frames=1000, fps=FPS, channel_count=3,
                    excluded_channels=())
    assert m["summary"]["total_spikes"] == 0
    assert m["summary"]["mean_rate_hz"] == 0.0
    for r in m["channels"]:
        assert r["isi_mean_ms"] is None
    # JSON-safe: no NaN anywhere
    import json
    json.dumps(m, allow_nan=False)


def test_compare_metrics():
    ts, ch = _spikes()
    a = compute_all(ts, ch, n_frames=1000, fps=FPS, channel_count=5, excluded_channels=(0,))
    b = compute_all(ts, ch, n_frames=1000, fps=FPS, channel_count=5, excluded_channels=(0,))
    assert compare_metrics(a, b) == []
    b["summary"]["total_spikes"] += 1
    assert compare_metrics(a, b) == ["/summary/total_spikes: 8 != 9"]
