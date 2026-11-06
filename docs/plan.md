# Implementation plan: local MVP (idea A)

Approved by Michael on 2026-11-06, with the revisions he listed in the project thread. All data in this milestone comes from the cl-sdk simulator. Nothing here runs on, or says anything about, living neurons.

## Scope

A command-line tool that runs one bounded simulator session, records it to HDF5, checks the recording, computes activity metrics, and writes a manifest and a self-contained static HTML report. It needs no AWS account, credentials or AWS libraries.

Out of scope for this milestone: stimulation experiments, closed-loop logic, web applications, dashboards, databases, any cloud resource. The AWS artifact layer is a written proposal only ([aws-proposal.md](aws-proposal.md)).

## Acquisition window and alignment

Each run happens in a fresh child process, so the simulator always starts at device frame 0. The acquisition window is device frames `[0, N)`, where `N = seconds x frames_per_second`. The recording is started with `Neurons.record(from_timestamp=0)` and stopped once frame `N` exists; the file may hold a few frames past `N`, which the canonical extraction drops.

The start offset is `CL_SDK_REPLAY_START_OFFSET`: the position in the source stream that maps to device frame 0. It must always be set. Without it the simulator picks a random start position on every `cl.open()`, and the same seed gives different data (observed on 2026-11-06, see [discovery.md](discovery.md)).

## Integrity checks

A run is `complete` only if every error-level check passes; otherwise it is `incomplete` (recording exists but fails a check) or `failed` (no usable recording). Incomplete and failed runs keep their folder, files and logs, and every output is marked with the status.

Error-level checks: recording start timestamp equals the window start; sample rows equal `duration_frames`; `duration_frames >= N`; sample columns equal `channel_count`; sample dtype is int16; spike timestamps lie in `[0, duration_frames)` and are sorted; spike channels lie in `[0, channel_count)`; the worker log has no "fell behind ring buffer" message; no unexpected `CL_SDK_*` variables reached the simulator.

Warning-level check: a run of 25 or more consecutive frames in which every non-ground channel is exactly zero (a possible gap).

## Reproducibility

Runs are compared on canonical data, not whole HDF5 files: the int16 sample block for frames `[0, N)`, and the spikes in that window as (timestamp, channel) pairs sorted by timestamp then channel. Each has a SHA-256 digest over a documented byte layout. Metrics are compared value by value.

The manifest records the seed, start offset, timing mode, window, all `CL_SDK_*` variables the simulator saw, the cl-sdk version, Python version, platform, every installed package version, and the workbench version and git commit.

## Acceptance criteria

1. A fresh virtual environment built from `requirements-lock.txt` installs and runs on Python 3.12 or later (tested on 3.13.18 and 3.12.3 in the cloud container; Windows steps untested until run).
2. `workbench run --seconds 5 --seed 42` finishes in wall-clock mode and writes `recording.h5`, `manifest.json`, `metrics.json`, `channel_metrics.csv` and `report.html` into a new run folder with a unique ID.
3. Two runs with the same seed, start offset and window have identical canonical sample and spike digests and identical metrics, including one wall-clock and one accelerated run.
4. A run with a different seed has different canonical sample data. No claim is made that every metric changes.
5. Metric and integrity functions pass unit tests on hand-built arrays with known answers, without starting the simulator.
6. A run whose recording fails an integrity check is kept and marked `incomplete`, and its report says so at the top.
7. Every output carries a SYNTHETIC or REPLAYED label, and the report states it is not biological data.
8. `pytest` passes; the SDK integration tests finish in under 2 minutes.
9. The report HTML loads no external resources.

## Steps

1. Pure modules first: metrics, integrity, canonical digests, with unit tests.
2. Child-process recorder and parent orchestration, manifest, failure handling.
3. Static HTML report.
4. CLI (`run`, `verify`, `compare`, `report`), README, architecture and licensing notes.
5. Integration tests against the installed SDK; smoke run; determinism check.
6. AWS proposal document. No resources created.
