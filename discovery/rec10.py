import cl
from cl.util import RecordingView
with cl.open() as neurons:
    rec = neurons.record(stop_after_seconds=10, file_location="rec", file_suffix="check")
    rec.wait_until_stopped()
with RecordingView(rec.file["path"]) as rv:
    a = rv.attributes
    print("duration_frames", a["duration_frames"], "samples rows", rv.samples.shape[0], "spikes", len(rv.spikes))
