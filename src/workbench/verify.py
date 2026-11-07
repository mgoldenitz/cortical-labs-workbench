"""`workbench verify`: check a run folder against the reference values its manifest recorded.

This is a consistency check, not authentication: it shows whether the files in a run
folder still match what that run's own manifest says. Anyone who edits both the
files and the manifest can make them agree, and nothing here identifies who
produced a run.

Exit codes:

    0  EXIT_OK            status is "complete", the manifest is well formed, every
                          required output is listed and present, every listed file
                          matches its recorded size and SHA-256, and the canonical
                          digests and metrics digest recomputed from the files match.
    1  EXIT_INCONSISTENT  the folder cannot be verified: manifest missing or not valid
                          JSON, required fields missing or malformed, empty or missing
                          file inventory, a required output missing, or any size,
                          checksum or digest mismatch.
    2  EXIT_NOT_COMPLETE  the files are consistent with the manifest, but the recorded
                          status is "running", "incomplete" or "failed": not a verified
                          complete run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import canonical, manifest as mf

EXIT_OK = 0
EXIT_INCONSISTENT = 1
EXIT_NOT_COMPLETE = 2

STATUSES = ("running", "complete", "incomplete", "failed")
# Written before the worker starts, so every run that got that far has them.
REQUIRED_ALWAYS = ("config.json", "worker.log")
REQUIRED_COMPLETE = ("config.json", "worker.log", "worker_result.json", "recording.h5",
                     "metrics.json", "channel_metrics.csv", "report.html")
CANONICAL_KEYS = ("window_frames", "n_spikes", "samples_sha256", "spikes_sha256")
_HEX64 = re.compile(r"[0-9a-f]{64}")


def _check_manifest(m) -> list[str]:
    """Structural problems with a manifest; empty when it is well formed."""
    if not isinstance(m, dict):
        return ["manifest.json is not a JSON object"]
    problems = []
    if m.get("schema") != mf.MANIFEST_SCHEMA:
        problems.append(f"schema is {m.get('schema')!r}, expected {mf.MANIFEST_SCHEMA!r}")
    if not isinstance(m.get("run_id"), str) or not m["run_id"]:
        problems.append("run_id missing")
    if "status" not in m:
        problems.append("status missing")
    elif m["status"] not in STATUSES:
        problems.append(f"unknown status {m['status']!r}")
    files = m.get("files")
    if not isinstance(files, dict):
        problems.append("file inventory ('files') missing")
    elif not files:
        problems.append("file inventory ('files') is empty")
    else:
        for name, entry in files.items():
            if not isinstance(name, str) or Path(name).name != name or name in ("", ".", ".."):
                problems.append(f"file inventory has an invalid name {name!r}")
            elif not (isinstance(entry, dict) and isinstance(entry.get("sha256"), str)
                      and _HEX64.fullmatch(entry["sha256"]) and isinstance(entry.get("bytes"), int)):
                problems.append(f"file inventory entry for {name} needs sha256 and bytes")
    if m.get("status") == "complete":
        c = m.get("canonical")
        if not isinstance(c, dict) or any(k not in c for k in CANONICAL_KEYS):
            problems.append("complete run without canonical digests")
        if not isinstance(m.get("metrics_sha256"), str):
            problems.append("complete run without metrics_sha256")
        integ = m.get("integrity")
        if not isinstance(integ, dict) or integ.get("errors"):
            problems.append("status is complete but the recorded integrity checks are missing or failed")
    return problems


def verify_run(run_dir: Path) -> tuple[int, list[str]]:
    """Return (exit code, lines to print)."""
    run_dir = Path(run_dir)
    path = run_dir / "manifest.json"
    if not path.is_file():
        return EXIT_INCONSISTENT, [f"VERIFY FAILED: no manifest.json in {run_dir}"]
    try:
        m = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return EXIT_INCONSISTENT, [f"VERIFY FAILED: manifest.json is not valid JSON ({exc})"]

    status = m.get("status") if isinstance(m, dict) else None
    lines = [f"status recorded in manifest: {status}"]
    problems = _check_manifest(m)
    if problems:
        return EXIT_INCONSISTENT, lines + ["VERIFY FAILED (manifest):", *[f"  {p}" for p in problems]]

    files = m["files"]
    required = REQUIRED_COMPLETE if status == "complete" else REQUIRED_ALWAYS
    problems += [f"required output {name} is not in the file inventory" for name in required
                 if name not in files]
    for name, entry in files.items():
        p = run_dir / name
        if not p.is_file():
            problems.append(f"missing file {name}")
        elif p.stat().st_size != entry["bytes"]:
            problems.append(f"size mismatch: {name}")
        elif mf.sha256_file(p) != entry["sha256"]:
            problems.append(f"checksum mismatch: {name}")

    if not problems and isinstance(m.get("canonical"), dict) and "recording.h5" in files:
        from .recording_io import load_recording
        try:
            rec = load_recording(run_dir / "recording.h5")
            canon = canonical.canonicalize(rec.samples, rec.spike_ts, rec.spike_ch,
                                           int(m["canonical"]["window_frames"]))
            d = canonical.digests(canon)
            for k in ("samples_sha256", "spikes_sha256", "n_spikes"):
                if d[k] != m["canonical"].get(k):
                    problems.append(f"canonical {k} differs from manifest")
        except Exception as exc:  # unreadable recording is a verification failure, not a crash
            problems.append(f"could not recompute canonical digests: {type(exc).__name__}: {exc}")
    if not problems and isinstance(m.get("metrics_sha256"), str) and "metrics.json" in files:
        try:
            metrics = json.loads((run_dir / "metrics.json").read_text())
            core = {"summary": metrics["summary"], "channels": metrics["channels"]}
            if mf.metrics_digest(core) != m["metrics_sha256"]:
                problems.append("metrics digest differs from manifest")
        except Exception as exc:
            problems.append(f"could not recompute metrics digest: {type(exc).__name__}: {exc}")

    unlisted = sorted(p.name for p in run_dir.iterdir()
                      if p.is_file() and p.name != "manifest.json" and p.name not in files)
    if unlisted:
        lines.append(f"note: files not in the manifest (not checked): {', '.join(unlisted)}")
    if problems:
        return EXIT_INCONSISTENT, lines + ["VERIFY FAILED:", *[f"  {p}" for p in problems]]
    if status != "complete":
        return EXIT_NOT_COMPLETE, lines + [
            f"NOT VERIFIED AS COMPLETE: the files match the manifest, but the run status is {status!r}."]
    return EXIT_OK, lines + [
        "verify OK: complete run; every listed file, the canonical digests and the metrics digest match "
        "the manifest. This checks consistency with the manifest only; it does not authenticate who "
        "produced the run."]
