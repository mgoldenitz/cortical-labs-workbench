import sys, glob, numpy as np
from cl.util import RecordingView
def load(tag):
    f = glob.glob(f"*{tag}.h5")[0]
    with RecordingView(f) as rv:
        return np.array(rv.samples[:75000]), np.array(rv.spikes[:])
for a, b in [("acc1","acc2"), ("wall1","wall2"), ("acc1","wall1")]:
    s1, p1 = load(a); s2, p2 = load(b)
    eq = np.array_equal(s1, s2)
    diffrows = np.where((s1 != s2).any(axis=1))[0]
    print(a, b, "samples equal:", eq, "n diff rows:", len(diffrows), "first diff:", diffrows[:3])
    t1 = set(map(tuple, np.c_[p1["timestamp"], p1["channel"]][p1["timestamp"]<75000])); t2 = set(map(tuple, np.c_[p2["timestamp"], p2["channel"]][p2["timestamp"]<75000]))
    print("   spikes:", len(t1), len(t2), "common", len(t1 & t2), "first only-in-a", sorted(t1-t2)[:3], "first only-in-b", sorted(t2-t1)[:3])
