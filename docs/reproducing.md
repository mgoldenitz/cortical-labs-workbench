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
