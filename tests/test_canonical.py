import numpy as np
import pytest

from workbench.canonical import canonicalize, digests, samples_digest, spikes_digest


def _data():
    samples = (np.arange(40, dtype=np.int16).reshape(10, 4) - 20)
    ts = np.array([7, 2, 2, 12, -1])
    ch = np.array([1, 3, 0, 2, 1])
    return samples, ts, ch


def test_trims_window_and_orders_spikes():
    c = canonicalize(*_data(), n_frames=8)
    assert c.samples.shape == (8, 4) and c.samples.dtype == np.dtype("<i2")
    assert c.spike_ts.tolist() == [2, 2, 7]   # 12 and -1 are outside [0, 8)
    assert c.spike_ch.tolist() == [0, 3, 1]   # ties broken by channel


def test_input_spike_order_does_not_matter():
    s, ts, ch = _data()
    perm = np.array([3, 0, 4, 2, 1])
    a = digests(canonicalize(s, ts, ch, 8))
    b = digests(canonicalize(s, ts[perm], ch[perm], 8))
    assert a == b


def test_frames_after_window_do_not_matter():
    s, ts, ch = _data()
    s2 = s.copy()
    s2[9] = 999
    assert samples_digest(canonicalize(s, ts, ch, 8)) == samples_digest(canonicalize(s2, ts, ch, 8))


def test_single_sample_change_changes_digest():
    s, ts, ch = _data()
    s2 = s.copy()
    s2[3, 1] += 1
    assert samples_digest(canonicalize(s, ts, ch, 8)) != samples_digest(canonicalize(s2, ts, ch, 8))


def test_digest_byte_layout_is_stable():
    # Locks the documented v1 byte layout. If this fails, bump CANONICAL_VERSION.
    c = canonicalize(*_data(), n_frames=8)
    assert samples_digest(c) == "8c26bfbe1382a087a8fa690e335b526b4b33e85fd62c25f62e386dc573a7e269"
    assert spikes_digest(c) == "afeb13803caaa06ce00b301dd62037f005bac98199742604fc50495d1ff56ea0"


def test_short_recording_rejected():
    with pytest.raises(ValueError):
        canonicalize(*_data(), n_frames=11)
