"""Recording integrity checks. Pure functions over attributes and arrays.

Each check returns a dict: {"name", "passed", "severity" ("error"|"warning"), "detail"}.
A run is "complete" only if every error-level check passes.
"""

from __future__ import annotations

import numpy as np

FELL_BEHIND_MARKER = "fell behind ring buffer"
ZERO_RUN_WARN_FRAMES = 25  # 1 ms at 25 kHz


def _check(name: str, passed: bool, detail: str, severity: str = "error") -> dict:
    return {"name": name, "passed": bool(passed), "severity": severity, "detail": detail}


def longest_zero_run(samples: np.ndarray, signal_channels: list[int]) -> tuple[int, int]:
    """Longest run of consecutive frames where every signal channel is exactly 0.

    Returns (length, start_frame); (0, -1) if there is none.
    """
    if samples.shape[0] == 0 or not signal_channels:
        return 0, -1
    zero = np.all(samples[:, signal_channels] == 0, axis=1).astype(np.int8)
    if not zero.any():
        return 0, -1
    padded = np.concatenate(([0], zero, [0]))
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    lengths = ends - starts
    i = int(np.argmax(lengths))
    return int(lengths[i]), int(starts[i])


def check_recording(
    *,
    attributes: dict,
    samples: np.ndarray,
    spike_ts: np.ndarray,
    spike_ch: np.ndarray,
    window_start: int,
    window_frames: int,
    non_signal_channels: tuple[int, ...],
    worker_log: str = "",
    unexpected_env: dict | None = None,
) -> list[dict]:
    checks: list[dict] = []
    start_ts = attributes.get("start_timestamp")
    checks.append(_check(
        "start_aligned", start_ts == window_start,
        f"recording start_timestamp={start_ts}, expected {window_start}",
    ))
    duration = int(attributes.get("duration_frames", -1))
    rows = int(samples.shape[0]) if samples is not None else -1
    checks.append(_check(
        "rows_match_duration", rows == duration,
        f"{rows} sample rows, duration_frames={duration}",
    ))
    checks.append(_check(
        "window_covered", duration >= window_frames and rows >= window_frames,
        f"recording has {min(rows, duration)} usable frames, window needs {window_frames}",
    ))
    channel_count = int(attributes.get("channel_count", -1))
    cols = int(samples.shape[1]) if samples is not None and samples.ndim == 2 else -1
    checks.append(_check(
        "channel_count", cols == channel_count and channel_count > 0,
        f"{cols} sample columns, channel_count={channel_count}",
    ))
    dtype = str(samples.dtype) if samples is not None else "none"
    checks.append(_check("samples_int16", dtype == "int16", f"samples dtype {dtype}"))

    ts = np.asarray(spike_ts, dtype=np.int64)
    ch = np.asarray(spike_ch, dtype=np.int64)
    in_bounds = bool(ts.size == 0 or (ts.min() >= 0 and ts.max() < max(duration, 0)))
    checks.append(_check(
        "spike_timestamps_in_bounds", in_bounds,
        f"{ts.size} spikes, range [{ts.min() if ts.size else '-'}, {ts.max() if ts.size else '-'}], "
        f"allowed [0, {duration})",
    ))
    sorted_ok = bool(ts.size < 2 or np.all(np.diff(ts) >= 0))
    checks.append(_check("spike_timestamps_sorted", sorted_ok, "spike timestamps non-decreasing" if sorted_ok
                         else "spike timestamps go backwards"))
    ch_ok = bool(ch.size == 0 or (ch.min() >= 0 and ch.max() < channel_count))
    checks.append(_check("spike_channels_valid", ch_ok, f"spike channels within [0, {channel_count})"))

    fell_behind = FELL_BEHIND_MARKER in worker_log.lower()
    checks.append(_check(
        "no_ring_buffer_overrun", not fell_behind,
        "worker log reports the recording fell behind the ring buffer (data lost)" if fell_behind
        else "no overrun reported by the SDK",
    ))
    unexpected_env = unexpected_env or {}
    checks.append(_check(
        "no_unexpected_sdk_env", not unexpected_env,
        f"unexpected CL_SDK_* variables reached the simulator: {sorted(unexpected_env)}" if unexpected_env
        else "only workbench-controlled CL_SDK_* variables were set",
    ))

    if samples is not None and samples.ndim == 2 and cols > 0:
        signal = [c for c in range(cols) if c not in non_signal_channels]
        run_len, run_start = longest_zero_run(samples, signal)
        checks.append(_check(
            "no_zero_gap", run_len < ZERO_RUN_WARN_FRAMES,
            f"longest all-zero run on signal channels: {run_len} frames"
            + (f" starting at frame {run_start}" if run_len else ""),
            severity="warning",
        ))
    return checks


def status_from_checks(checks: list[dict]) -> str:
    return "complete" if all(c["passed"] for c in checks if c["severity"] == "error") else "incomplete"
