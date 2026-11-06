#!/usr/bin/env bash
# Rebuild the reproducibility evidence in docs/evidence/ from a clean clone.
#
# Usage: tools/run_evidence.sh PYTHON_EXE OUT_DIR
#   PYTHON_EXE  interpreter to build the venv with, e.g. python3.13 or python3.12
#   OUT_DIR     where logs and the sample run go (created; must not exist)
#
# Run it from a clean checkout of the commit you want to test. It never deletes anything.
set -euo pipefail
PY="$1"; OUT="$2"
mkdir "$OUT"
OUT="$(cd "$OUT" && pwd)"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

{
  echo "commit: $(git rev-parse HEAD)"
  echo "dirty:  $(if [ -n "$(git status --porcelain --untracked-files=no)" ]; then echo yes; else echo no; fi)"
  echo "date:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host:   $(uname -srm), $(nproc) CPUs"
} > "$OUT/context.txt"

VENV="$OUT/venv"
"$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install -q -r requirements-lock.txt
"$VENV/bin/python" -m pip install -q --no-deps -e .
"$VENV/bin/python" --version >> "$OUT/context.txt"
"$VENV/bin/python" -m pip freeze --exclude-editable > "$OUT/pip-freeze.txt"

# 1. Full test suite.
"$VENV/bin/python" -m pytest -v -p no:cacheprovider 2>&1 | tee "$OUT/pytest.log"

# 2. Determinism: two wall-clock runs and one accelerated run, 5 s, seed 42.
RUNS="$OUT/runs"
for mode in "" "" "--accelerated"; do
  "$VENV/bin/workbench" run --seconds 5 --seed 42 $mode --out "$RUNS" | tee -a "$OUT/runs.log"
done
mapfile -t DIRS < <(ls -d "$RUNS"/*/)
{
  echo "== wall clock vs wall clock"; "$VENV/bin/workbench" compare "${DIRS[0]}" "${DIRS[1]}" || true
  echo "== wall clock vs accelerated"; "$VENV/bin/workbench" compare "${DIRS[0]}" "${DIRS[2]}" || true
  echo "== verify first run"; "$VENV/bin/workbench" verify "${DIRS[0]}" || true
} 2>&1 | tee "$OUT/compare.log"

# 3. Known issue: 10 s accelerated run (expected INCOMPLETE, exit code 2).
"$VENV/bin/workbench" run --seconds 10 --seed 42 --accelerated --out "$OUT/known-issue" 2>&1 \
  | tee "$OUT/known-issue.log" || true

echo "evidence written to $OUT"
