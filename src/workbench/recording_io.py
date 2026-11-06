"""Read a recording through the SDK's public RecordingView API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


def _plain(value):
    """Convert numpy scalars and nested containers into JSON-friendly Python values."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


@dataclass
class LoadedRecording:
    attributes: dict
    samples: np.ndarray
    spike_ts: np.ndarray
    spike_ch: np.ndarray
    n_stims: int


def load_recording(path: Path) -> LoadedRecording:
    from cl.util import RecordingView  # public API (also exported as cl.RecordingView)

    with RecordingView(str(path)) as rv:
        attributes = _plain(dict(rv.attributes))
        samples = np.asarray(rv.samples[:]) if rv.samples is not None else np.empty((0, 0), np.int16)
        if rv.spikes is not None and len(rv.spikes):
            spikes = rv.spikes[:]
            spike_ts = np.asarray(spikes["timestamp"], dtype=np.int64)
            spike_ch = np.asarray(spikes["channel"], dtype=np.int64)
        else:
            spike_ts = np.empty(0, np.int64)
            spike_ch = np.empty(0, np.int64)
        n_stims = int(len(rv.stims)) if rv.stims is not None else 0
    return LoadedRecording(attributes, samples, spike_ts, spike_ch, n_stims)
