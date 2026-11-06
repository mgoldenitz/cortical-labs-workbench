"""Canonical data: the part of a recording that reproducibility is judged on.

Whole HDF5 files differ between identical runs (creation times, file paths, a few
extra frames after the window). Runs are therefore compared on:

* samples: the int16 block for frames [0, N) of the recording, all channels;
* spikes: (timestamp, channel) for spikes with 0 <= timestamp < N, sorted by
  timestamp then channel. Spike waveforms are not included: they are cut from the
  samples, which are already covered.

Digest byte layout, version 1 (all integers little-endian):

    samples: b"cl-workbench/samples/v1" | n_frames:u64 | n_channels:u64 | samples:int16[n_frames, n_channels] C-order
    spikes:  b"cl-workbench/spikes/v1"  | n_spikes:u64 | timestamps:int64[n] | channels:int64[n]
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

CANONICAL_VERSION = 1


@dataclass(frozen=True)
class CanonicalData:
    samples: np.ndarray       # int16 [n_frames, n_channels]
    spike_ts: np.ndarray      # int64 [n]
    spike_ch: np.ndarray      # int64 [n]

    @property
    def n_frames(self) -> int:
        return int(self.samples.shape[0])


def canonicalize(samples: np.ndarray, spike_ts: np.ndarray, spike_ch: np.ndarray, n_frames: int) -> CanonicalData:
    """Trim to the window [0, n_frames) and put spikes in canonical order."""
    samples = np.asarray(samples)
    if samples.ndim != 2:
        raise ValueError(f"samples must be 2-D, got shape {samples.shape}")
    if samples.shape[0] < n_frames:
        raise ValueError(f"recording has {samples.shape[0]} frames, window needs {n_frames}")
    window = np.ascontiguousarray(samples[:n_frames], dtype="<i2")
    ts = np.asarray(spike_ts, dtype=np.int64)
    ch = np.asarray(spike_ch, dtype=np.int64)
    keep = (ts >= 0) & (ts < n_frames)
    ts, ch = ts[keep], ch[keep]
    order = np.lexsort((ch, ts))
    return CanonicalData(samples=window, spike_ts=ts[order], spike_ch=ch[order])


def samples_digest(data: CanonicalData) -> str:
    h = hashlib.sha256(b"cl-workbench/samples/v1")
    h.update(np.array(data.samples.shape, dtype="<u8").tobytes())
    h.update(data.samples.astype("<i2", copy=False).tobytes(order="C"))
    return h.hexdigest()


def spikes_digest(data: CanonicalData) -> str:
    h = hashlib.sha256(b"cl-workbench/spikes/v1")
    h.update(np.array([data.spike_ts.size], dtype="<u8").tobytes())
    h.update(data.spike_ts.astype("<i8", copy=False).tobytes())
    h.update(data.spike_ch.astype("<i8", copy=False).tobytes())
    return h.hexdigest()


def digests(data: CanonicalData) -> dict:
    return {
        "canonical_version": CANONICAL_VERSION,
        "window_frames": data.n_frames,
        "n_channels": int(data.samples.shape[1]),
        "n_spikes": int(data.spike_ts.size),
        "samples_sha256": samples_digest(data),
        "spikes_sha256": spikes_digest(data),
    }
