# cl-workbench

A small command-line tool for the [Cortical Labs CL SDK](https://github.com/Cortical-Labs/cl-sdk) simulator. It records one seeded simulator session to HDF5, checks the recording, computes spike metrics, and writes a manifest and a self-contained HTML report. In the tested environments (Linux x86_64, Python 3.12.3 and 3.13.18, cl-sdk 1.0.0 with the pinned packages), repeated runs with the same data source, seed, start offset and window produced identical canonical samples, spikes and metrics, in wall-clock and accelerated mode for windows up to 5 s. `workbench compare` reports whether two runs match. Other platforms, versions or settings have not been checked.

## Simulated data, not neurons

Everything this tool produces comes from the cl-sdk simulator running on an ordinary computer. No CL1 hardware, Cortical Cloud account or living cells are involved.

- SYNTHETIC runs use the simulator's random source: Poisson noise, with samples above a percentile threshold labelled as spikes.
- REPLAYED runs loop an existing HDF5 file through the simulator. REPLAYED names the input mode only: it says nothing about where that file came from, and a replay is not a new live or biological experiment. The manifest records the source file's path, size and SHA-256 under `acquisition.replay_source`.
- The simulator does not respond to stimulation and does not learn. Cortical Labs' documentation says so, and a test in [docs/discovery.md](docs/discovery.md) confirmed stimulation leaves the data byte-identical.

Firing rates, intervals and other metrics in a report describe the simulator's output. They are useful as software tests and as a null baseline. They are not evidence about biological neurons, learning, intelligence or responses to stimulation. Results from real CL1 hardware would need their own provenance and would be labelled differently; this version cannot produce any.

## Setup

Requires Python 3.12 or later (cl-sdk 1.0.0 requirement). Tested on Python 3.13.18 and 3.12.3, Linux x86_64.

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

`workbench verify` reopens a complete run folder and checks it against the reference values its own manifest recorded: the SHA-256 of every listed file, and the canonical sample and spike digests recomputed from `recording.h5`. It detects files that changed, went missing or no longer match the recorded data. It does not authenticate who produced the run and is not a digital signature: anyone who edits both the files and the manifest can make them agree.

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
- Run stopped with Ctrl-C: `manifest.json` is set to `failed` and no report is written.
- Process killed outright (or the machine stopped): `manifest.json` may still say `running`, and later files are absent.
- If the report itself cannot be rendered, the manifest records `report_error` and `report.html` may be missing.

## Tests

```bash
pytest                 # all 47 tests, about 13 s
pytest -m "not sdk"    # only tests that do not start the simulator
```

The `sdk` tests start the simulator in child processes: repeated runs with the same seed must produce identical canonical data and metrics (including wall-clock against accelerated), a different seed must change the sample data, a replay must reproduce its source frames, tampering must be caught by `verify`, and failed or overrun runs must be kept and marked.

## Documentation

- [docs/plan.md](docs/plan.md): scope and acceptance criteria for this milestone
- [docs/architecture.md](docs/architecture.md): modules, acquisition window, canonical digests, run status
- [docs/discovery.md](docs/discovery.md): what was checked, versions, observed SDK behaviour; scripts in `discovery/`
- [docs/known-issues.md](docs/known-issues.md): accelerated-mode data loss, with versions and reproduction steps
- [docs/reproducing.md](docs/reproducing.md): exact commands for the Python 3.12 and 3.13 test runs and the determinism evidence; logs in [docs/evidence/](docs/evidence/). The run folders there are sanitized partial bundles (the recordings are left out and scratch paths are redacted), so they are not expected to pass `workbench verify`; see [docs/evidence/REDACTION.md](docs/evidence/REDACTION.md)
- [docs/licensing.md](docs/licensing.md) and [docs/third-party-licenses.md](docs/third-party-licenses.md): third-party licenses
- [docs/project-license-options.md](docs/project-license-options.md): options for this project's own license (none chosen)
- [docs/aws-proposal.md](docs/aws-proposal.md): proposed optional AWS storage and execution (nothing provisioned)

## Known limitations

- cl-sdk is pinned to 1.0.0. The electrode layout comes from a private SDK module (`src/workbench/layout.py`), which a future release may change.
- Accelerated mode lost the start of every 10 s and 30 s recording tried in the test environment ([docs/known-issues.md](docs/known-issues.md)); wall-clock mode is the default.
- No stimulation or closed-loop features yet; the simulator would not respond to them.
- The project's own code has no license yet; options are in [docs/project-license-options.md](docs/project-license-options.md).
