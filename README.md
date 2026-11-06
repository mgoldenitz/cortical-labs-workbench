# cl-workbench

A small command-line tool for the [Cortical Labs CL SDK](https://github.com/Cortical-Labs/cl-sdk) simulator. It records one seeded simulator session to HDF5, checks the recording, computes spike metrics, and writes a manifest and a self-contained HTML report. Runs with the same settings reproduce the same canonical data, and the tool can prove it.

## Simulated data, not neurons

Everything this tool produces comes from the cl-sdk simulator running on an ordinary computer. No CL1 hardware, Cortical Cloud account or living cells are involved.

- SYNTHETIC runs use the simulator's random source: Poisson noise, with samples above a percentile threshold labelled as spikes.
- REPLAYED runs loop an existing HDF5 file.
- The simulator does not respond to stimulation and does not learn. Cortical Labs' documentation says so, and a test in [docs/discovery.md](docs/discovery.md) confirmed stimulation leaves the data byte-identical.

Firing rates, intervals and other metrics in a report describe the simulator's output. They are useful as software tests and as a null baseline. They are not evidence about biological neurons, learning, intelligence or responses to stimulation. Results from real CL1 hardware would need their own provenance and would be labelled differently; this version cannot produce any.

## Setup

Requires Python 3.12 or later (cl-sdk 1.0.0 requirement). Tested on Python 3.13.18 and 3.12.3, Linux x86_64.

```bash
git clone https://github.com/mgoldenitz/cortical-labs-workbench.git
cd cortical-labs-workbench
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
pip install --no-deps -e .
```

On Windows (untested so far): use `py -3.13 -m venv .venv` and `.venv\Scripts\activate`, then the same two `pip install` lines.

`requirements-lock.txt` pins every package, including `cl-sdk==1.0.0`; it was generated with `uv pip compile pyproject.toml --extra test --universal --python-version 3.12`. Installing cl-sdk means accepting its license, CC BY-NC 4.0 (non-commercial); see [docs/licensing.md](docs/licensing.md).

No credentials, `.env` file or network access are needed at run time. The simulator's local visualisation server is always switched off.

## Use

```bash
workbench run --seconds 5 --seed 42          # wall-clock mode, about 7 s
workbench verify runs/<run_id>               # re-check files and digests against the manifest
workbench compare runs/<run_a> runs/<run_b>  # same canonical data and metrics?
```

`run` options: `--start-offset FRAMES` (position in the source stream, default 0), `--accelerated` (faster; complete up to 5 s in tests, but lost data on every 10 s and 30 s recording tried, and such runs are marked incomplete), `--replay FILE.h5`, `--bin-ms`, `--active-hz`, `--out DIR` (default `runs/`). Exit code 0 means the run is complete, 2 means incomplete or failed.

Each run gets its own folder, `runs/<UTC time>-s<seed>-<random>/`:

| File | Contents |
| --- | --- |
| `report.html` | The report: settings, summary metrics, raster, population rate, firing rate on the 8x8 electrode grid, interval histogram, integrity checks, digests |
| `manifest.json` | Status, seed, offset, window, timing mode, every `CL_SDK_*` variable the simulator saw, cl-sdk and Python versions, all installed packages, workbench version and git commit, integrity results, digests, file checksums |
| `metrics.json`, `channel_metrics.csv` | Metrics over the canonical window |
| `recording.h5` | The simulator's HDF5 recording |
| `worker.log`, `worker_result.json`, `config.json` | What the simulator process printed and observed |

Runs that fail a check are kept and marked `incomplete` or `failed` in every file; nothing is deleted.

## Tests

```bash
pytest                 # all tests, about 15 s
pytest -m "not sdk"    # only tests that do not start the simulator
```

The `sdk` tests start the simulator in child processes: repeated runs with the same seed must produce identical canonical data and metrics (including wall-clock against accelerated), a different seed must change the sample data, a replay must reproduce its source frames, tampering must be caught by `verify`, and failed or overrun runs must be kept and marked.

## Documentation

- [docs/plan.md](docs/plan.md): scope and acceptance criteria for this milestone
- [docs/architecture.md](docs/architecture.md): modules, acquisition window, canonical digests, run status
- [docs/discovery.md](docs/discovery.md): what was checked, versions, observed SDK behaviour; scripts in `discovery/`
- [docs/licensing.md](docs/licensing.md) and [docs/third-party-licenses.md](docs/third-party-licenses.md)
- [docs/aws-proposal.md](docs/aws-proposal.md): proposed optional AWS storage and execution (nothing provisioned)

## Known limitations

- cl-sdk is pinned to 1.0.0. The electrode layout comes from a private SDK module (`src/workbench/layout.py`), which a future release may change.
- Accelerated mode lost the start of every 10 s and 30 s recording tried; wall-clock mode is the default.
- No stimulation or closed-loop features yet; the simulator would not respond to them.
- The project's own code has no license yet.
