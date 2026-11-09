# cl-workbench

A small command-line tool for the [Cortical Labs CL SDK](https://github.com/Cortical-Labs/cl-sdk) simulator. It records one seeded simulator session to HDF5, checks the recording, computes spike metrics, and writes a manifest and a self-contained HTML report. In the tested environments (Linux x86_64, Python 3.12.3 and 3.13.18, cl-sdk 1.0.0 with the pinned packages), repeated runs with the same data source, seed, start offset and window produced identical canonical samples, spikes and metrics, in wall-clock and accelerated mode for windows up to 5 s. `workbench compare` reports whether two runs match. Other platforms, versions or settings have not been checked.

## Simulated data, not neurons

Everything this tool produces comes from the cl-sdk simulator running on an ordinary computer. No CL1 hardware, Cortical Cloud account or living cells are involved.

- SYNTHETIC runs use the simulator's random source: Poisson noise, with samples above a percentile threshold labelled as spikes.
- REPLAYED runs loop an existing HDF5 file through the simulator. REPLAYED names the input mode only: it says nothing about where that file came from, and a replay is not a new live or biological experiment. The manifest records the source file's path, size and SHA-256 under `acquisition.replay_source`.
- The simulator does not respond to stimulation and does not learn. Cortical Labs' documentation says so, and a test in [docs/discovery.md](docs/discovery.md) confirmed stimulation leaves the data byte-identical.

Firing rates, intervals and other metrics in a report describe the simulator's output. They are useful as software tests and as a null baseline. They are not evidence about biological neurons, learning, intelligence or responses to stimulation. Results from real CL1 hardware would need their own provenance and would be labelled differently; this version cannot produce any.

## Setup

Requires Python 3.12 or later (cl-sdk 1.0.0 requirement). Tested environment: cl-sdk 1.0.0 with the package versions in `requirements-lock.txt`, Python 3.13.18 and 3.12.3, Ubuntu 24.04 x86_64 (a 4-CPU cloud container, and GitHub's ubuntu-24.04 runners for CI). Nothing has been tested on macOS or Windows, and stopping leftover simulator processes is not supported there (see below).

Name the interpreter when you create the virtual environment, so the version is not left to whatever `python3` points to. Linux or macOS (only Linux has been tested):

```bash
git clone https://github.com/mgoldenitz/cortical-labs-workbench.git
cd cortical-labs-workbench
python3.13 -m venv .venv          # or python3.12
source .venv/bin/activate
python --version                  # check it says 3.12 or 3.13
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
```

Windows is untested. The commands below are the standard ones for each shell, not steps anyone has run with this project.

Windows PowerShell:

```powershell
py -3.13 -m venv .venv            # or py -3.12
.venv\Scripts\Activate.ps1        # if scripts are blocked, see PowerShell's execution policy help
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
```

Windows Command Prompt:

```bat
py -3.13 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
```

`requirements-lock.txt` pins every package, including `cl-sdk==1.0.0`; it was generated with `uv pip compile pyproject.toml --extra test --universal --python-version 3.12`. Installing cl-sdk means accepting its license, CC BY-NC 4.0 (non-commercial); see [docs/licensing.md](docs/licensing.md).

No credentials, `.env` file or network access are needed at run time. The simulator's local visualisation server is always switched off.

## Use

```bash
workbench run --seconds 5 --seed 42          # wall-clock mode, about 7 s
workbench verify runs/<run_id>               # re-check a complete run against its manifest
workbench compare runs/<run_a> runs/<run_b>  # same canonical data and metrics?
```

`run` options: `--start-offset FRAMES` (position in the source stream, default 0), `--accelerated` (faster; complete up to 5 s in tests, but lost data on every 10 s and 30 s recording tried, and such runs are marked incomplete), `--replay FILE.h5`, `--bin-ms`, `--active-hz`, `--out DIR` (default `runs/`). Exit code 0 means the run is complete, 2 means incomplete or failed.

`run` ends by printing the run folder, its status, the canonical digests and the report's location, for example:

```
run:    runs/20261106T220121Z-s42-20a15f
status: COMPLETE  (SYNTHETIC data)
samples sha256:  a9ce19c8e3fc3655c99aebe350bcc8888515a9214100c6b76886e7dea4a11e0f
spikes sha256:   0253017365645a7f8233121abfb5bef1cd25d7058dfef28415cf962cd70de810  (342 spikes)
report: runs/20261106T220121Z-s42-20a15f/report.html
```

The report is a single HTML file with no external resources. Open the path on the `report:` line in any browser, for example with `xdg-open` on Linux, `open` on macOS, or `start` in a Windows shell, or by double-clicking it in a file manager.

`workbench verify` reopens a run folder and checks it against the reference values its own manifest recorded: the manifest's required fields, the file inventory (which must exist and not be empty, and for a complete run must list every output), the size and SHA-256 of every listed file, the canonical sample and spike digests recomputed from `recording.h5`, and the metrics digest recomputed from `metrics.json`. Files in the folder that the manifest does not list are named but not checked. Exit codes:

- 0: the status is `complete` and everything above matches.
- 1: invalid or inconsistent, so the folder cannot be verified: no manifest, a manifest that is not valid JSON or is missing required fields, an unknown status, a missing or empty file inventory, a missing required output, or any size, checksum or digest mismatch.
- 2: consistent but not complete: the files match the manifest, but the recorded status is `running`, `incomplete` or `failed`, so this is not a verified complete run.

So 1 means the evidence in the folder is invalid or does not match its own manifest, and 2 means the evidence is intact but records a run that did not complete.

Verification checks consistency, not authenticity. It does not authenticate who produced the run and is not a digital signature: anyone who edits both the files and the manifest can make them agree.

Each run gets its own folder, `runs/<UTC time>-s<seed>-<random>/`:

| File | Contents |
| --- | --- |
| `report.html` | The report: settings, summary metrics, raster, population rate, firing rate on the 8x8 electrode grid, interval histogram, integrity checks, digests |
| `manifest.json` | Status, seed, offset, window, timing mode, every `CL_SDK_*` variable the simulator saw, cl-sdk and Python versions, all installed packages, workbench version and git commit, integrity results, digests, file checksums |
| `metrics.json`, `channel_metrics.csv` | Metrics over the canonical window |
| `recording.h5` | The simulator's HDF5 recording |
| `worker.log`, `worker_result.json`, `config.json` | What the simulator process printed and observed |

Runs that fail are kept; nothing is deleted. The final status (`complete`, `incomplete` or `failed`) is in `manifest.json` (with `error` and the failed checks), in the status banner of `report.html`, in `metrics.json` when it is written, and in the `status:` line and exit code that `run` prints. `channel_metrics.csv`, `config.json`, `worker.log`, `worker_result.json` and `recording.h5` do not carry a status. What may be missing depends on how far the run got:

- Incomplete run whose recording does not cover the whole window (for example the accelerated-mode data loss): no `metrics.json` or `channel_metrics.csv`, and no canonical digests in the manifest.
- Failed run with no recording: no `recording.h5`, `metrics.json` or `channel_metrics.csv`; `worker_result.json` only if the simulator process got far enough to write it.
- Worker that runs past its timeout (by default three times the window plus 90 s): the worker and every simulator process it started are stopped, the run is marked `failed` with a "timed out" error, and the files written so far are kept, including the partial `recording.h5` if there is one.
- Run stopped with Ctrl-C while the simulator is recording: the worker and simulator processes are stopped the same way, `manifest.json` is set to `failed` with the error "interrupted by user", and no report is written. The folder keeps `config.json`, `worker.log`, `worker_result.json` (with the worker's `KeyboardInterrupt`) and, if recording had started, the SDK's `*_raw.h5` file under its original name. The manifest records the cleanup under `acquisition.worker.process_cleanup`, the same key as after a timeout, but gets no file inventory, so `workbench verify` exits with 1. This was tested on Linux by sending Ctrl-C through a pseudo-terminal ([docs/reproducing.md](docs/reproducing.md#ctrl-c-during-acquisition)). Ctrl-C later, during analysis or report writing, leaves `manifest.json` at `running`.
- Process killed outright (or the machine stopped): `manifest.json` may still say `running`, later files are absent, and simulator processes may be left running. `workbench verify` exits with 1 or 2 on such a folder, never 0.

- If the report itself cannot be rendered, the manifest records `report_error` and `report.html` may be missing.

Stopping simulator processes is implemented for Linux only. The cl-sdk simulator starts its helper processes in new sessions, so stopping the worker or its process group does not reach them. Every process of a run instead inherits the environment variable `CL_WORKBENCH_RUN_MARKER` set to the run id, and after the worker exits (or is stopped) the workbench finds processes carrying that marker through `/proc`, waits up to 3 s for them to exit on their own, then sends SIGTERM, waits up to 5 s, sends SIGKILL to any left and waits up to 2 s more. The manifest records the process ids found, terminated and killed under `acquisition.worker.process_cleanup`, and `remaining` should be empty. Process cleanup is unsupported on macOS and Windows: they have no `/proc`, the record says `"supported": false`, nothing is checked, and simulator processes may be left running after a timeout or Ctrl-C.

## Tests

```bash
pytest                 # all 94 tests, about 27 s
pytest -m "not sdk"    # only tests that do not start the simulator
```

The `sdk` tests start the simulator in child processes: repeated runs with the same seed must produce identical canonical data and metrics (including wall-clock against accelerated), a different seed must change the sample data, a replay must reproduce its source frames, tampering must be caught by `verify`, failed or overrun runs must be kept and marked, and a worker that times out must leave no worker or simulator process running. The other tests check `verify` on hand-built manifests (every status, missing or malformed fields, missing or empty inventories, missing outputs) and the process cleanup on a process tree that escapes its process group.

One failure is unexplained: `test_runs_complete_with_expected_outputs` failed once in 10 local runs on 2026-11-06 and its output was not captured. It did not recur in 30 later runs of the `sdk` tests or 10 runs of the full suite, and the cause is unknown. If it fails in CI, the job uploads the pytest log and the test run folders as an artifact.

## Documentation

- [docs/plan.md](docs/plan.md): scope and acceptance criteria for this milestone
- [docs/architecture.md](docs/architecture.md): modules, acquisition window, canonical digests, run status
- [docs/discovery.md](docs/discovery.md): what was checked, versions, observed SDK behaviour; scripts in `discovery/`
- [docs/known-issues.md](docs/known-issues.md): accelerated-mode data loss, with versions and reproduction steps
- [docs/reproducing.md](docs/reproducing.md): exact commands for the Python 3.12 and 3.13 test runs and the determinism evidence; logs in [docs/evidence/](docs/evidence/). The run folders there are sanitized partial bundles (the recordings are left out and scratch paths are redacted), so they are not expected to pass `workbench verify`; see [docs/evidence/REDACTION.md](docs/evidence/REDACTION.md)
- [docs/licensing.md](docs/licensing.md) and [docs/third-party-licenses.md](docs/third-party-licenses.md): third-party licenses
- [docs/project-license-options.md](docs/project-license-options.md): the license options that were considered (MIT was chosen)
- [docs/aws-proposal.md](docs/aws-proposal.md): proposed optional AWS storage and execution (nothing provisioned)

## License

The workbench's original code is licensed under the MIT License; see [LICENSE](LICENSE). cl-sdk is a separate package under its own license, CC BY-NC 4.0, and is not included in this repository. The MIT License covers only this project's code and does not grant any rights to use cl-sdk beyond cl-sdk's own license terms. Commercial use involving cl-sdk, CL1 hardware or Cortical Labs services may require separate permission from Cortical Labs. Details are in [docs/licensing.md](docs/licensing.md).

## Known limitations

- cl-sdk is pinned to 1.0.0. The electrode layout comes from a private SDK module (`src/workbench/layout.py`), which a future release may change.
- Accelerated mode lost the start of every 10 s and 30 s recording tried in the test environment ([docs/known-issues.md](docs/known-issues.md)); wall-clock mode is the default.
- One intermittent test failure is unexplained (see Tests).
- Process cleanup after a timeout or Ctrl-C works on Linux only.
- No stimulation or closed-loop features yet; the simulator would not respond to them.
