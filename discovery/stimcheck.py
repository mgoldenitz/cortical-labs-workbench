"""Fresh process: read fixed absolute window [50000, 75000) with or without prior stim. Synthetic data."""
import sys, hashlib, numpy as np, cl
stim = sys.argv[1] == "stim"
START = 50_000
with cl.open() as neurons:
    t0 = neurons.timestamp()
    if stim:
        for ch in range(64):
            if ch in (0, 4, 7, 56, 63): continue
            neurons.stim(ch, cl.StimDesign(160, -2.0, 160, 2.0), cl.BurstDesign(10, 100))
    f = neurons.read(25_000, START)
    r = neurons.read(25_000, START, analysis=True)
print(f"mode={sys.argv[1]} t0={t0} sha={hashlib.sha256(f.tobytes()).hexdigest()[:16]} spikes={len(r.spikes)} mean={f.mean():.3f}")
