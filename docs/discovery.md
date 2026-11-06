# Discovery results (2026-11-06)

Observed results from the discovery phase and from building the MVP. Every number here came from a command that ran in the cloud container (Linux x86_64, 4 CPUs, 15 GiB RAM, Python 3.13.18, cl-sdk 1.0.0 from PyPI). All data was synthetic (the simulator's random source) unless marked replayed. The scripts are in [`../discovery/`](../discovery/); they are records of what ran, not part of the package.

## Sources checked

| Source | Version checked |
| --- | --- |
| [Cortical-Labs/cl-sdk](https://github.com/Cortical-Labs/cl-sdk) | commit `a9a2f9c0cefaa032075d7cd7ccbbc4b037ba1991` (tag v1.0.0, 2026-06-11) |
| cl-sdk on PyPI | 1.0.0; wheel `LICENSE` identical to the repo's (SHA-256 `55f908cd...e4fc`) |
| [Cortical-Labs/cl-api-doc](https://github.com/Cortical-Labs/cl-api-doc) | commit `a6726472cb3375ebcd836ec2dd239ebff7a1624a` (2025-08-30), README says "Pre-Release" |
| [docs.corticallabs.com](https://docs.corticallabs.com) | read 2026-11-06 through a browser (blocked from the container); text matches `docs/index.md` in cl-sdk at the commit above |
| CL API whitepaper | arXiv 2602.11632v1, PDF supplied by Michael, marked "Preview, subject to further changes" |

## What the simulator does and does not model

The official docs say the simulator "generates non-learning control data that does not respond to stimulation" and is for baseline controls only. The code agrees: the two built-in data sources (`RandomDataSource`, `FileRecordingDataSource` in `cl/sim/_data_source.py`) do not override `SimulatorDataSource.on_stim`, so stimulation never changes the data. The random source draws Poisson-distributed samples and labels percentile-threshold crossings as spikes.

## Observations

| # | Observation | Script |
| --- | --- | --- |
| 1 | Notebook code from cl-api-doc CL-00, CL-01 and CL-02 runs unchanged on cl-sdk 1.0.0 (run lengths shortened). 64 channels, 25,000 frames/s, int16 samples, 0.195 uV per unit. | `smoke.py` |
| 2 | Stimulating 59 channels with 10-pulse 100 Hz bursts left frames 50,000 to 75,000 byte-identical to a run without stimulation. | `stimcheck.py` |
| 3 | With `CL_SDK_RANDOM_SEED` and `CL_SDK_REPLAY_START_OFFSET` both set, fresh processes produce identical frames. | `stimcheck.py`, `align.py` |
| 4 | Without `CL_SDK_REPLAY_START_OFFSET`, the random source also starts at a random position on each `cl.open()`, so the same seed gives different data. The README describes this randomisation only for replay. | `align.py` + `cmp.py` |
| 5 | `Neurons.record(from_timestamp=0)` in a fresh process gives a recording with `start_timestamp` 0. Its docstring says `from_*` arguments are not used by the simulator, but `cl/recording.py` (around line 198) honours them. | `align.py` |
| 6 | Same seed and offset: identical canonical samples and spikes between wall-clock and accelerated mode for 3 s and 5 s windows. | `align.py`, `workbench compare` |
| 7 | Accelerated mode loses the start of longer recordings. A 10 s recording kept 131,072 of 250,001 rows and the SDK printed "Recording fell behind ring buffer (cursor=0, buf_start=118929)"; the first spike in the file is at frame 119,134. This happened in 5 of 5 workbench runs at 10 s and 30 s. 1 s, 3 s and 5 s accelerated runs were complete. Wall-clock 10 s recordings were complete. | `rec10.py`, `workbench run --accelerated` |
| 8 | The kept rows in a failed accelerated recording are shifted: the file still says `start_timestamp` 0, but the data starts near frame 119,000. The workbench catches this through `rows_match_duration`, `window_covered` and `no_ring_buffer_overrun`, not through `start_aligned`. | workbench runs |
| 9 | Simulator recordings leave `git_hash`, `git_branch`, `git_status` empty, set `hostname` to `cl-sdk` and `file_format.version` to `SDK`. | `smoke.py`, workbench manifests |
| 10 | Running the cloned cl-sdk repo's own pytest suite was blocked by the session's permission checker as external code. It was not worked around. | (not run) |

Unverified hypothesis for observation 7: the simulator's ring buffer holds about 131,072 frames (2^17, 5.24 s), and in accelerated mode the data producer gets that far ahead before the recording process starts reading. Not confirmed from the source.

## Whitepaper points that affect this project

Table 1, item 5.5: simulator and hardware share API semantics; they differ in timing resolution and latency, and the simulator may accept transactions that hardware rejects for capacity reasons. Item 5.7 lists "deterministic biological responses" among things the API does not guarantee. On a CL1 a 25 kHz loop body has about 33 to 34 us before `TimeoutError` (section 6.2); the simulator only warns.
