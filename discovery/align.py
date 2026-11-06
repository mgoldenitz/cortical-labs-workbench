import sys, time, hashlib, os, numpy as np, cl
from cl.util import RecordingView
N = int(sys.argv[1]); tag = sys.argv[2]
with cl.open() as neurons:
    t_open = neurons.timestamp()
    rec = neurons.record(from_timestamp=0, file_location=os.getcwd(), file_suffix=tag)
    t_rec = neurons.timestamp()
    neurons.read(1, N)          # blocks until frame N exists
    rec.stop()
    t_stop = neurons.timestamp()
with RecordingView(rec.file["path"]) as rv:
    a = rv.attributes
    s = rv.samples[:N]
    sp = rv.spikes[:]
    spk = sp[sp["timestamp"] < N]
    h = hashlib.sha256(np.ascontiguousarray(s).tobytes() + spk["timestamp"].tobytes() + spk["channel"].tobytes()).hexdigest()[:16]
    print(f"{tag} t_open={t_open} t_rec={t_rec} t_stop={t_stop} start_ts={a['start_timestamp']} dur={a['duration_frames']} rows={rv.samples.shape[0]} spikes<N={len(spk)} canon={h}")
