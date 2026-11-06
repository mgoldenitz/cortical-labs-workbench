"""Activity metrics computed from canonical spike data.

Pure numpy, no SDK import, so every function can be tested on hand-built arrays.

Units: timestamps are frames relative to the window start; rates are Hz; inter-spike
intervals (ISI) are milliseconds; bins are milliseconds.

On simulator data these numbers describe the simulator's random generator or a
replayed file. They are not measurements of living neurons.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

METRICS_VERSION = 1


@dataclass(frozen=True)
class MetricsConfig:
    active_rate_threshold_hz: float = 0.1
    population_bin_ms: float = 100.0
    min_spikes_for_isi_cv: int = 3


def _finite_or_none(x: float) -> float | None:
    return None if x is None or not math.isfinite(x) else float(x)


def channel_metrics(
    spike_ts: np.ndarray,
    spike_ch: np.ndarray,
    *,
    n_frames: int,
    fps: int,
    channel_count: int,
    excluded_channels: tuple[int, ...] = (),
    config: MetricsConfig = MetricsConfig(),
) -> list[dict]:
    """Per-channel spike count, rate, ISI mean and ISI coefficient of variation.

    ``excluded_channels`` (ground, reference) are reported but flagged, and left
    out of population summaries.
    """
    if n_frames <= 0 or fps <= 0:
        raise ValueError("n_frames and fps must be positive")
    spike_ts = np.asarray(spike_ts, dtype=np.int64)
    spike_ch = np.asarray(spike_ch, dtype=np.int64)
    if spike_ts.shape != spike_ch.shape:
        raise ValueError("spike_ts and spike_ch must have the same shape")
    duration_s = n_frames / fps
    rows = []
    for ch in range(channel_count):
        ts = np.sort(spike_ts[spike_ch == ch])
        n = int(ts.size)
        isi_ms = np.diff(ts) / fps * 1000.0
        isi_mean = float(isi_ms.mean()) if isi_ms.size else math.nan
        if n >= config.min_spikes_for_isi_cv and isi_mean > 0:
            isi_cv = float(isi_ms.std(ddof=0) / isi_mean)
        else:
            isi_cv = math.nan
        rate = n / duration_s
        rows.append(
            {
                "channel": ch,
                "excluded": ch in excluded_channels,
                "spike_count": n,
                "rate_hz": float(rate),
                "active": bool(rate >= config.active_rate_threshold_hz) and ch not in excluded_channels,
                "isi_mean_ms": _finite_or_none(isi_mean),
                "isi_cv": _finite_or_none(isi_cv),
            }
        )
    return rows


def population_rate(
    spike_ts: np.ndarray, *, n_frames: int, fps: int, bin_ms: float
) -> tuple[np.ndarray, np.ndarray]:
    """Spike counts in consecutive bins of ``bin_ms``. Returns (bin_start_s, counts).

    A trailing partial bin is dropped so every bin has the same width.
    """
    bin_frames = int(round(bin_ms / 1000.0 * fps))
    if bin_frames <= 0:
        raise ValueError("bin_ms too small for this sampling rate")
    n_bins = n_frames // bin_frames
    ts = np.asarray(spike_ts, dtype=np.int64)
    ts = ts[(ts >= 0) & (ts < n_bins * bin_frames)]
    counts = np.bincount(ts // bin_frames, minlength=n_bins).astype(np.int64)
    starts = np.arange(n_bins) * bin_frames / fps
    return starts, counts


def summarize(
    rows: list[dict],
    spike_ts: np.ndarray,
    spike_ch: np.ndarray,
    *,
    n_frames: int,
    fps: int,
    config: MetricsConfig = MetricsConfig(),
) -> dict:
    """Population-level summary over non-excluded channels (excluded channels' spikes are left out)."""
    included = [r for r in rows if not r["excluded"]]
    rates = np.array([r["rate_hz"] for r in included], dtype=float)
    included_set = np.array(sorted(r["channel"] for r in included), dtype=np.int64)
    total = int(sum(r["spike_count"] for r in included))
    mask = np.isin(np.asarray(spike_ch, dtype=np.int64), included_set)
    _, counts = population_rate(
        np.asarray(spike_ts, dtype=np.int64)[mask], n_frames=n_frames, fps=fps,
        bin_ms=config.population_bin_ms,
    )
    bin_s = config.population_bin_ms / 1000.0
    return {
        "metrics_version": METRICS_VERSION,
        "duration_s": n_frames / fps,
        "n_frames": int(n_frames),
        "frames_per_second": int(fps),
        "channels_included": len(included),
        "channels_excluded": sorted(r["channel"] for r in rows if r["excluded"]),
        "active_channels": int(sum(r["active"] for r in included)),
        "active_rate_threshold_hz": config.active_rate_threshold_hz,
        "total_spikes": total,
        "mean_rate_hz": _finite_or_none(float(rates.mean())) if rates.size else None,
        "median_rate_hz": _finite_or_none(float(np.median(rates))) if rates.size else None,
        "max_rate_hz": _finite_or_none(float(rates.max())) if rates.size else None,
        "population_bin_ms": config.population_bin_ms,
        "population_rate_mean_hz": _finite_or_none(float(counts.mean() / bin_s)) if counts.size else None,
        "population_rate_max_hz": _finite_or_none(float(counts.max() / bin_s)) if counts.size else None,
        "population_rate_n_bins": int(counts.size),
    }


def compute_all(
    spike_ts: np.ndarray,
    spike_ch: np.ndarray,
    *,
    n_frames: int,
    fps: int,
    channel_count: int,
    excluded_channels: tuple[int, ...],
    config: MetricsConfig = MetricsConfig(),
) -> dict:
    rows = channel_metrics(
        spike_ts, spike_ch, n_frames=n_frames, fps=fps, channel_count=channel_count,
        excluded_channels=excluded_channels, config=config,
    )
    summary = summarize(rows, spike_ts, spike_ch, n_frames=n_frames, fps=fps, config=config)
    return {"summary": summary, "channels": rows}


def compare_metrics(a: dict, b: dict) -> list[str]:
    """Return human-readable differences between two metrics dicts (empty if identical)."""
    diffs: list[str] = []

    def walk(x, y, path):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x or k not in y:
                    diffs.append(f"{path}/{k}: present in only one run")
                else:
                    walk(x[k], y[k], f"{path}/{k}")
        elif isinstance(x, list) and isinstance(y, list):
            if len(x) != len(y):
                diffs.append(f"{path}: length {len(x)} != {len(y)}")
            for i, (xi, yi) in enumerate(zip(x, y)):
                walk(xi, yi, f"{path}[{i}]")
        elif x != y:
            diffs.append(f"{path}: {x!r} != {y!r}")

    walk(a, b, "")
    return diffs
