"""Discovery smoke test against installed cl-sdk (simulator only). Synthetic data."""
import os, sys, time, hashlib
import numpy as np
import cl

print("cl-sdk is_simulator:", cl.is_simulator())

def h(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()[:16]

# 1. CL-00 Hello, Neurons (verbatim stim calls)
with cl.open() as neurons:
    print("channels", neurons.get_channel_count(), "fps", neurons.get_frames_per_second())
    neurons.stim(cl.ChannelSet(27), cl.StimDesign(180, -1.5, 180, 1.5))
    neurons.stim(cl.ChannelSet(27, 28, 35, 36), cl.StimDesign(180, -1.5, 180, 1.5))
    neurons.stim(cl.ChannelSet(27, 28, 35, 36), cl.StimDesign(160, -2, 320, 1, 160, -2), cl.BurstDesign(14, 50))
print("CL-00 stim calls: OK")

# 2. CL-01 closed loop, shortened to 2 s
n_spikes = n_stims = 0
with cl.open() as neurons:
    for tick in neurons.loop(ticks_per_second=1000, stop_after_seconds=2):
        for spike in tick.analysis.spikes:
            n_spikes += 1
            neurons.stim(spike.channel, 1); n_stims += 1
print(f"CL-01 loop 2s: spikes={n_spikes} stims_issued={n_stims}")

# 3. CL-02 recording 1 s + RecordingView analysis
os.makedirs("rec", exist_ok=True)
with cl.open() as neurons:
    rec = neurons.record(stop_after_seconds=1, file_location="rec")
    rec.wait_until_stopped()
a = rec.attributes
print("CL-02 recorded frames", a["duration_frames"], "seconds", a["duration_seconds"], "file", rec.file["path"])
from cl.util import RecordingView
with RecordingView(rec.file["path"]) as rv:
    print("samples shape", rv.samples.shape, "dtype", rv.samples.dtype, "spikes", len(rv.spikes))
    fs = rv.analyse_firing_stats()
    print("firing stats type", type(fs).__name__)

# 4. Determinism + stim-independence: read same timestamps with and without stim
def read_window(stim_first):
    with cl.open() as neurons:
        t0 = neurons.timestamp()
        start = t0 + 2500
        if stim_first:
            for ch in range(1, 63):
                if ch in (4, 7, 56): continue
                neurons.stim(ch, cl.StimDesign(160, -2.0, 160, 2.0), cl.BurstDesign(10, 100))
        frames = neurons.read(25000, start)
        res = neurons.read(25000, start, analysis=True)
        return start, frames, len(res.spikes)
s1, f1, k1 = read_window(False)
s2, f2, k2 = read_window(False)
s3, f3, k3 = read_window(True)
print("start ts", s1, s2, s3, "shape", f1.shape, f1.dtype)
print("hash no-stim run1", h(f1), "run2", h(f2), "with-stim", h(f3))
print("spikes no-stim", k1, k2, "with-stim", k3)
print("identical runs:", s1 == s2 and np.array_equal(f1, f2))
print("stim changed data:", not (s1 == s3 and np.array_equal(f1, f3)))
