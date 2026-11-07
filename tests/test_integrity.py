import numpy as np

from workbench.integrity import check_recording, longest_zero_run, status_from_checks

NON_SIGNAL = (0, 3)


def _good(n=200, ch=4):
    rng = np.random.default_rng(0)
    samples = rng.integers(-50, 50, size=(n, ch)).astype(np.int16)
    samples[:, list(NON_SIGNAL)] = 0
    samples[samples == 0] = 1
    samples[:, list(NON_SIGNAL)] = 0
    attrs = {"start_timestamp": 0, "duration_frames": n, "channel_count": ch}
    return attrs, samples, np.array([5, 50, 120]), np.array([1, 2, 1])


def _run(**over):
    attrs, samples, ts, ch = _good()
    kw = dict(attributes=attrs, samples=samples, spike_ts=ts, spike_ch=ch, window_start=0,
              window_frames=150, non_signal_channels=NON_SIGNAL)
    kw.update(over)
    checks = check_recording(**kw)
    return {c["name"]: c for c in checks}, status_from_checks(checks)


def test_good_recording_is_complete():
    checks, status = _run()
    assert status == "complete"
    assert all(c["passed"] for c in checks.values())


def test_misaligned_start_is_incomplete():
    attrs, *_ = _good()
    checks, status = _run(attributes={**attrs, "start_timestamp": 4890})
    assert not checks["start_aligned"]["passed"] and status == "incomplete"


def test_row_count_mismatch_is_incomplete():
    # the accelerated-mode failure seen on 2026-11-06: fewer rows than duration_frames
    attrs, *_ = _good()
    checks, status = _run(attributes={**attrs, "duration_frames": 250})
    assert not checks["rows_match_duration"]["passed"] and status == "incomplete"


def test_window_not_covered():
    checks, status = _run(window_frames=500)
    assert not checks["window_covered"]["passed"] and status == "incomplete"


def test_spike_bounds_order_and_channels():
    checks, _ = _run(spike_ts=np.array([5, 300]), spike_ch=np.array([1, 1]))
    assert not checks["spike_timestamps_in_bounds"]["passed"]
    checks, _ = _run(spike_ts=np.array([50, 5]), spike_ch=np.array([1, 1]))
    assert not checks["spike_timestamps_sorted"]["passed"]
    checks, _ = _run(spike_ts=np.array([5]), spike_ch=np.array([9]))
    assert not checks["spike_channels_valid"]["passed"]


def test_wrong_dtype():
    attrs, samples, ts, ch = _good()
    checks, status = _run(samples=samples.astype(np.float32))
    assert not checks["samples_int16"]["passed"] and status == "incomplete"


def test_ring_buffer_overrun_in_log():
    log = "Recording fell behind ring buffer (cursor=0, buf_start=118928). Some data was lost."
    checks, status = _run(worker_log=log)
    assert not checks["no_ring_buffer_overrun"]["passed"] and status == "incomplete"


def test_unexpected_env():
    checks, status = _run(unexpected_env={"CL_SDK_DATA_SOURCE": "x:y"})
    assert not checks["no_unexpected_sdk_env"]["passed"] and status == "incomplete"


def test_zero_gap_is_a_warning_only():
    attrs, samples, ts, ch = _good()
    samples[100:140, :] = 0
    checks, status = _run(samples=samples)
    assert not checks["no_zero_gap"]["passed"]
    assert checks["no_zero_gap"]["severity"] == "warning"
    assert status == "complete"


def test_longest_zero_run():
    s = np.ones((10, 3), np.int16)
    s[2:4] = 0
    s[6:9] = 0
    s[6:9, 0] = 7  # channel 0 is non-signal, so it does not break the run
    assert longest_zero_run(s, [1, 2]) == (3, 6)
    assert longest_zero_run(np.ones((5, 2), np.int16), [0, 1]) == (0, -1)
