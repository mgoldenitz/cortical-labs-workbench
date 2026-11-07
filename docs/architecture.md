# Architecture

```
workbench run (parent process)                     python -m workbench._worker (child process)
-----------------------------                     ------------------------------------------
config.RunConfig ──► pipeline.run                  fresh simulator, device frame 0
   │                   │  writes manifest.json      CL_SDK_* env set by parent only
   │                   │  (status "running")        cl.open()
   │                   ├──── subprocess ──────────► Neurons.record(from_timestamp=0)
   │                   │                            Neurons.read(1, N)   # wait for frame N
   │                   │                            Recording.stop()
   │                   │◄─── worker_result.json ──── recording *_raw.h5, worker.log
   │                   ▼
   │           pipeline.finalize
   │             recording_io.load_recording   (public cl.util.RecordingView)
   │             integrity.check_recording     (pure numpy)
   │             canonical.canonicalize/digests (pure numpy)
   │             metrics.compute_all           (pure numpy)
   │             report.render_report          (matplotlib, static HTML)
   │             manifest.json (final status, checksums)
   ▼
runs/<run_id>/
```

## Modules

| Module | Job | Imports cl-sdk? |
| --- | --- | --- |
| `config.py` | Run settings and the exact `CL_SDK_*` variables they map to | no |
| `_worker.py` | The only code that opens the simulator | yes, public API |
| `pipeline.py` | Starts the worker, collects results, runs the analysis, writes the manifest; never deletes a run folder | indirectly |
| `procs.py` | Finds and stops a run's processes by an inherited environment marker (Linux `/proc` only) | no |
| `verify.py` | `workbench verify`: manifest structure, file inventory, checksums, recomputed digests; exit codes 0, 1, 2 | no |
| `recording_io.py` | Reads HDF5 through `cl.util.RecordingView` | yes, public API |
| `layout.py` | Electrode grid, ground and reference channels | yes, private module, isolated here |
| `integrity.py` | Recording checks | no |
| `canonical.py` | Canonical window extraction and digests | no |
| `metrics.py` | Spike metrics | no |
| `manifest.py` | Environment, code version, checksums | no |
| `report.py` | Static HTML with embedded PNG figures | no |
| `cli.py` | `run`, `verify`, `compare` | no |

Logic that can be tested without the simulator (integrity, canonical, metrics, report) lives in modules that take plain arrays. The SDK is confined to `_worker.py`, `recording_io.py` and `layout.py`.

## Why a child process per run

Inside one Python process the simulator keeps running between `cl.open()` calls, so the second session starts at whatever frame the first reached (observed: 77,500, then 105,000, then 132,500). A fresh process always starts at frame 0, which makes the acquisition window absolute. It also lets the parent control the simulator's environment completely: inherited `CL_SDK_*` variables are dropped, the workbench sets every documented option explicitly, the worker runs with its working directory set to the run folder, and the worker reports back every `CL_SDK_*` variable it saw after importing `cl` (which loads `.env` files). Any variable the workbench did not set fails the `no_unexpected_sdk_env` check.

The simulator's own helper processes (for example `cl-data-producer`) are started by cl-sdk with `start_new_session=True`, so they leave the worker's process group and are re-parented when the worker dies. Before 2026-11-06 a worker timeout left them running. The parent now sets `CL_WORKBENCH_RUN_MARKER=<run_id>` in the worker's environment, every simulator process inherits it, and `procs.stop_marked` finds them through `/proc/<pid>/environ` after the worker exits or is stopped, with a bounded settle, SIGTERM, SIGKILL sequence (at most about 10 s). This is Linux only.

## Acquisition window and alignment

Window: device frames `[0, N)`, `N = round(seconds x 25,000)`. The recording starts with `from_timestamp=0`, which reads the frames produced between `cl.open()` and the `record()` call back out of the simulator's buffer (about 0.2 s of wall-clock time in tests). The worker stops the recording after frame `N` exists, so files hold `N` plus a few frames; canonical extraction trims to `N`.

Where the extra frames come from (checked in cl-sdk 1.0.0 source and run output): `Neurons.read(1, N)` returns once frame `N` exists, that is once the simulator's write timestamp is at least `N + 1`. `Recording.stop()` then ends the recording at the write timestamp at the moment it is called. In wall-clock mode the data producer writes 5 frames per tick (`DEFAULT_TICK_RATE_HZ = 5000` in `cl/_sim/_data_producer.py`: one 200 us tick is 5 frames at 25 kHz; the source comment there says "2ms ticks", which does not match 5 kHz), so frames `[N, N+5)` arrive together and the recording ends at `N + 5`: every 5 s wall-clock run so far has `duration_frames = 125005`. In accelerated mode the producer advances exactly to the requested timestamp, so recordings end at `N + 1`. The overshoot is not guaranteed to be 5: a delay between the two calls would add more. It does not matter for results, because everything downstream uses only frames `[0, N)`:

- `canonical.canonicalize` keeps `samples[:N]` and spikes with `0 <= timestamp < N`;
- both digests are computed from that trimmed data (the samples digest also encodes the shape `N x 64`);
- metrics, `metrics_sha256` and every report figure are computed from the same trimmed data, with `n_frames = N`;
- `tests/test_sdk_integration.py::test_analysis_uses_exact_window` checks this on real runs: the file has more than `N` rows, while the digests recomputed from `samples[:N]`, the spike count for `timestamp < N` and `metrics.summary.n_frames` all match the manifest. `stop_after_frames` is not used because, with `from_timestamp` in the past, the SDK counts it from the call time.

`CL_SDK_REPLAY_START_OFFSET` (the `--start-offset` option, default 0) chooses which part of the source stream lands at frame 0. It is always set, because without it the simulator picks a random start on each open. For replays, offset 0 maps the source file's first frame to device frame 0 (tested: the first 12,500 frames match exactly).

## Canonical data and digests

Version 1 byte layout (little-endian):

```
samples digest = SHA-256( "cl-workbench/samples/v1" || u64 n_frames || u64 n_channels || int16[n_frames][n_channels] )
spikes digest  = SHA-256( "cl-workbench/spikes/v1"  || u64 n_spikes || int64 timestamps[n] || int64 channels[n] )
```

Spikes are those with `0 <= timestamp < N`, sorted by timestamp, then channel. Spike waveforms are left out because they are cut from the samples. `metrics_sha256` is SHA-256 of the metrics JSON (summary and channels) with sorted keys and no whitespace. Whole HDF5 files are not compared: they contain creation times, run IDs and a variable number of trailing frames.

Same seed, same offset and same window gave identical canonical digests and metrics across repeated runs and across wall-clock and accelerated mode (1 s, 3 s and 5 s windows). A different seed gave different sample data in every case tried; the code does not assume every metric must change.

## Integrity checks and run status

`complete`: all error-level checks pass. `incomplete`: a recording exists but at least one error-level check failed; metrics are computed only if the window is fully covered; the status is recorded in `manifest.json`, the report banner and `metrics.json` (when written), as the README lists. `failed`: no usable recording, or analysis raised; the folder keeps the manifest, worker log and a report stating the error. The check list is in `docs/plan.md` and `src/workbench/integrity.py`.

## Timing

Wall-clock mode is the default. Accelerated mode is available with `--accelerated`; it lost the first ~119,000 frames of every 10 s and 30 s recording tried, and the checks mark those runs incomplete (see discovery.md, observations 7 and 8). Python here has no hard real-time guarantee, and the simulator does not enforce the CL1's loop deadlines, so no timing result from this tool says anything about CL1 latency.
