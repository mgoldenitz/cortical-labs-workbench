# Reproducing the test runs and evidence

All evidence in [`evidence/`](evidence/) was produced on 2026-11-06 from a clean clone at commit `251d6cf9f26cc8b51057a39241794c63bff3901e` with no uncommitted changes (runs started 22:35 and 22:36 UTC), in a Linux x86_64 cloud container with 4 CPUs. The commit that adds this page and `evidence/` changes no code: `git diff 251d6cf HEAD -- src tests tools pyproject.toml requirements-lock.txt` is empty.

## Commands

From a fresh clone (`OUT` must not exist yet; the script creates it and never deletes anything):

```bash
git clone https://github.com/mgoldenitz/cortical-labs-workbench.git
cd cortical-labs-workbench
git checkout 251d6cf9f26cc8b51057a39241794c63bff3901e   # or the branch under review

tools/run_evidence.sh python3.13 /tmp/evidence-py313
tools/run_evidence.sh python3.12 /tmp/evidence-py312
```

`tools/run_evidence.sh` does, for the given interpreter:

1. `python -m venv OUT/venv`, then `pip install -r requirements-lock.txt` and `pip install --no-deps -e .`
2. `python -m pytest -v -p no:cacheprovider` (all 47 tests, including the simulator integration tests)
3. `workbench run --seconds 5 --seed 42` twice in wall-clock mode and once with `--accelerated`, then `workbench compare` on both pairs and `workbench verify` on the first run
4. `workbench run --seconds 10 --seed 42 --accelerated`, which reproduces the known issue and is expected to end `INCOMPLETE` with exit code 2

The interpreters used were Python 3.13.18 and Python 3.12.3 (`/usr/bin/python3.12`). Any 3.12 or 3.13 build should work; `uv python install 3.12` is one way to get one.

To run only the tests in an existing environment: `pytest` (about 13 s), or `pytest -m "not sdk"` to skip the tests that start the simulator.

## Results recorded on 2026-11-06

| | Python 3.13.18 | Python 3.12.3 |
| --- | --- | --- |
| Tests | 47 passed in 13.17 s | 47 passed in 12.51 s |
| 5 s runs, samples SHA-256 | `a9ce19c8e3fc3655c99aebe350bcc8888515a9214100c6b76886e7dea4a11e0f`, all 3 runs | same value, all 3 runs |
| 5 s runs, spikes SHA-256 | `0253017365645a7f8233121abfb5bef1cd25d7058dfef28415cf962cd70de810`, 342 spikes | same |
| 5 s runs, metrics SHA-256 | `984acb4f68aa9cb1ef8a8f77bc651be49dce4536d17dc3bfa7d0e4447e013a2b` | same |
| `compare`, wall clock vs wall clock | identical | identical |
| `compare`, wall clock vs accelerated | identical | identical |
| `verify` on first run | OK | OK |
| 10 s accelerated run | INCOMPLETE (3 failed checks) | INCOMPLETE (3 failed checks) |
| Installed packages | `py313/pip-freeze.txt` | identical versions (`py312/pip-freeze.txt`) |

So canonical data and metrics matched across repeated runs, across timing modes and across the two Python versions.

## Files in `evidence/`

- `py313/`, `py312/`: `context.txt` (commit, dirty flag, date, host, Python), `pip-freeze.txt`, `pytest.log`, `runs.log`, `compare.log`, `known-issue.log`, and `known-issue-run/` (manifest, worker log and worker result of the incomplete 10 s run). `known-issue-run/` is a partial bundle and does not include the recording, config or report.
- `sample-run/`: every output of the first Python 3.13 run except `recording.h5` (16.6 MB, left out as bulky generated data). Its `report.html` shows commit `251d6cf...` with no uncommitted changes. It is a partial bundle. `workbench verify` supports only complete run folders, so on this folder it reports the missing recording and cannot recompute the canonical digests; the manifest still lists the recording's checksum.

The absolute container scratch path was replaced by `<evidence>` in 13 files here (six logs and seven JSON files) after the runs finished. The manifests keep their original checksums, so `config.json` and `worker_result.json` no longer match them. [`evidence/REDACTION.md`](evidence/REDACTION.md) lists the edited files with their original and published checksums. [`evidence/SHA256SUMS`](evidence/SHA256SUMS) holds the checksums of the published files; check it with `cd docs/evidence && sha256sum -c SHA256SUMS`.

## Ctrl-C during acquisition

`tools/ctrlc_pty_check.py` (Linux only) starts `workbench run --seconds 30` as the foreground job of a new pseudo-terminal, waits until the simulator's `cl-data-producer` process is running plus a chosen delay, and writes Ctrl-C (0x03) to the terminal. The terminal turns it into SIGINT for its foreground process group, as a real terminal does. The script then reports the exit time, which processes carrying the run's `CL_WORKBENCH_RUN_MARKER` were alive before and after, the recorded status, the files kept and the `workbench verify` exit code, and fails if the exit took longer than 15 s, any marked process remains, or verify returned 0.

```bash
python tools/ctrlc_pty_check.py --out /tmp/ctrlc-check --delay 2
```

Results on 2026-11-07, source code as at commit `c6d4b0cc794a05e8dacad7ede9074eeedf29e9a4`, Python 3.13.18, Ubuntu 24.04, three runs with delays of 0.5 s, 2 s and 10 s after the data producer started:

| Delay | Marked processes before Ctrl-C (outside the foreground group) | Exit after Ctrl-C | Marked processes after exit, and 2 s later | Status and error | Files kept | `verify` |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 s | 4 (2) | 3.28 s | none, none | `failed`, "interrupted by user" | `config.json`, `manifest.json`, `worker.log`, `worker_result.json` | 1 |
| 2 s | 6 (4) | 0.38 s | none, none | `failed`, "interrupted by user" | the same plus the SDK's `*_raw.h5` | 1 |
| 10 s | 6 (4) | 0.39 s | none, none | `failed`, "interrupted by user" | the same plus the SDK's `*_raw.h5` | 1 |

In every run `workbench run` exited by SIGINT (exit status -2 as Python reports it, 130 in a shell) and printed a `KeyboardInterrupt` traceback. The processes outside the foreground group were the simulator's `cl-data-producer` helper, its `cl-recording-<id>` helper once recording had started, and a resource tracker for each, which a plain Ctrl-C does not reach. None of them was left afterwards; at this commit the run folder did not record whether they exited on their own or were stopped by the marker cleanup (see below). `worker_result.json` records the worker's `KeyboardInterrupt`. At this commit the manifest had no `process_cleanup` record after Ctrl-C (added later for issue #2; see below) and has no file inventory, so `verify` reports "file inventory ('files') missing" and exits with 1. Only Linux was tested; macOS and Windows have no `/proc`, and there the simulator's helpers may be left running.

After the fix for issue #2 the script also requires `acquisition.worker.process_cleanup` in the manifest, with `"supported": true` and `remaining` empty, and status `failed` with "interrupted by user". Three runs on 2026-11-07 (Python 3.13.18, Ubuntu 24.04), delays 0.5 s, 2 s and 10 s: each passed, exited within 3.4 s, left no marked process, and `verify` exited with 1. In each run the record listed two processes found and terminated with SIGTERM, none killed and none remaining. In the 2 s run, checked against the process list taken before Ctrl-C, those two were the worker and its resource tracker, which were still handling SIGINT; the simulator helpers outside the foreground group (`cl-data-producer`, `cl-recording-<id>` and their trackers) had already exited by the time of the scan.
