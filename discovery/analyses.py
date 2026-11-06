"""Record 10 s of synthetic (random-source) data, run each RecordingView analysis. Synthetic only."""
import time, cl
from cl.util import RecordingView
with cl.open() as neurons:
    rec = neurons.record(stop_after_seconds=10, file_location="rec", file_suffix="ten_s")
    rec.wait_until_stopped()
with RecordingView(rec.file["path"]) as rv:
    print("spikes in 10 s:", len(rv.spikes))
    for name in ["analyse_firing_stats","analyse_network_bursts","analyse_criticality","analyse_information_entropy",
                 "analyse_lempel_ziv_complexity","analyse_dct_features","analyse_spike_triggered_histogram","analyse_functional_connectivity"]:
        t=time.time()
        try:
            r = getattr(rv, name)() if name not in ("analyse_network_bursts","analyse_criticality","analyse_information_entropy","analyse_lempel_ziv_complexity","analyse_dct_features","analyse_spike_triggered_histogram","analyse_functional_connectivity") else None
            if r is None:
                import inspect; sig = inspect.signature(getattr(rv, name)); 
                req=[p for p in sig.parameters.values() if p.default is inspect._empty]
                r = getattr(rv, name)() if not req else f"needs args: {[p.name for p in req]}"
            print(f"{name}: {type(r).__name__ if not isinstance(r,str) else r} ({time.time()-t:.2f}s)")
        except Exception as e:
            print(f"{name}: ERROR {type(e).__name__}: {str(e)[:150]}")
