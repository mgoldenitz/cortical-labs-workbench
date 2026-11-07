"""One run end to end: child-process acquisition, integrity checks, metrics, manifest, report.

Run folder layout (runs/<run_id>/):

    config.json          settings sent to the worker
    worker.log           worker stdout/stderr (SDK messages, warnings)
    worker_result.json   what the worker observed (timestamps, CL_SDK_* env it saw)
    recording.h5         the HDF5 recording, renamed from the SDK's timestamped name
    metrics.json         summary + per-channel metrics over the canonical window
    channel_metrics.csv  per-channel metrics as CSV
    report.html          self-contained static report
    manifest.json        provenance, integrity results, digests, file checksums; written
                         first with status "running" and rewritten at the end

Folders are never deleted by this code. Failed or incomplete runs keep everything.
"""

from __future__ import annotations

import csv
import json
import os
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import canonical, integrity, manifest as mf, procs
from .config import WINDOW_START_FRAME, RunConfig
from .metrics import MetricsConfig, compute_all

EXPECTED_ENV_KEYS = {
    "CL_SDK_RANDOM_SEED", "CL_SDK_REPLAY_START_OFFSET", "CL_SDK_ACCELERATED_TIME",
    "CL_SDK_VISUALISATION", "CL_SDK_SAMPLE_MEAN", "CL_SDK_SPIKE_PERCENTILE",
    "CL_SDK_SPIKE_VISIBILITY", "CL_SDK_REPLAY_PATH",
}


def new_run_id(seed: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-s{seed}-{secrets.token_hex(3)}"


def unexpected_env(seen: dict, expected: dict) -> dict:
    """CL_SDK_* variables the worker saw that the workbench did not set, or set differently."""
    out = {}
    for k, v in seen.items():
        if k not in expected:
            out[k] = v
        elif expected[k] != v:
            out[k] = f"{v} (expected {expected[k]})"
    for k in expected:
        if k not in seen:
            out[k] = "(missing)"
    return out


def child_env(cfg: RunConfig, run_id: str | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CL_SDK_") and k != procs.RUN_MARKER_ENV}
    env.update(cfg.sdk_env())
    env["PYTHONUNBUFFERED"] = "1"
    if run_id:
        # Inherited by the worker and every simulator process it starts; used to find them for cleanup.
        env[procs.RUN_MARKER_ENV] = run_id
    return env


def _write_channel_csv(path: Path, rows: list[dict]) -> None:
    fields = ["channel", "excluded", "spike_count", "rate_hz", "active", "isi_mean_ms", "isi_cv"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r[k] is None else r[k]) for k in fields})


def acquire(cfg: RunConfig, run_dir: Path, run_id: str, timeout_s: float | None = None) -> dict:
    """Start the worker, wait for it, return its result dict (with returncode and log)."""
    # The worker runs with cwd=run_dir, so every path handed to it must be absolute.
    run_dir = run_dir.resolve()
    worker_cfg = {**cfg.to_dict(), "run_dir": str(run_dir), "run_id": run_id}
    (run_dir / "config.json").write_text(json.dumps(worker_cfg, indent=2))
    timeout_s = timeout_s or (cfg.seconds * 3 + 90)
    log_path = run_dir / "worker.log"
    timed_out = False
    interrupt = None
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "workbench._worker", str(run_dir / "config.json")],
            cwd=run_dir, env=child_env(cfg, run_id), stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            returncode = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
        except KeyboardInterrupt as exc:  # Ctrl-C: clean up below, then let it propagate
            interrupt = exc
            raise
        finally:
            # Stop the worker (on timeout or Ctrl-C) and any simulator process it left behind (always).
            cleanup = procs.stop_marked(run_id, settle_s=0 if proc.poll() is None else 3)
            if proc.poll() is None:  # not reachable through /proc, or ignored SIGKILL
                proc.kill()
            proc.wait(timeout=5)
            if interrupt is not None:
                # run() records this in the manifest before re-raising the interrupt.
                interrupt.process_cleanup = cleanup
        if timed_out:
            returncode = None
    result_path = run_dir / "worker_result.json"
    try:
        result = json.loads(result_path.read_text()) if result_path.exists() else {"ok": False}
    except json.JSONDecodeError:  # cut short mid-write
        result = {"ok": False, "error": "worker_result.json is not valid JSON"}
    result["returncode"] = returncode
    result["timed_out"] = timed_out
    result["process_cleanup"] = cleanup
    if timed_out:
        result["ok"] = False
        result["error"] = f"worker timed out after {timeout_s:.0f} s and was stopped"
    elif returncode != 0 and "error" not in result:
        result["ok"] = False
        result["error"] = f"worker exited with code {returncode}; see worker.log"
    result["log"] = log_path.read_text(errors="replace")
    return result


def _find_recording(run_dir: Path, result: dict) -> Path | None:
    if result.get("recording_path") and Path(result["recording_path"]).exists():
        return Path(result["recording_path"])
    candidates = sorted(run_dir.glob("*_raw.h5"))
    return candidates[-1] if candidates else None


def finalize(run_dir: Path, manifest: dict, *, worker_log: str, env_unexpected: dict, cfg: RunConfig,
             worker_error: str | None = None, timed_out: bool = False) -> dict:
    """Analyse the recording in run_dir and complete the manifest. Never raises for data problems."""
    from .layout import load_layout
    from .recording_io import load_recording
    from .report import render_report

    rec_path = run_dir / "recording.h5"
    metrics = canon = layout = None
    try:
        layout = load_layout()
        manifest["sdk"]["private_modules_used"] = [layout.source]
        rec = load_recording(rec_path)
        manifest["acquisition"]["recording_attributes"] = rec.attributes
        manifest["acquisition"]["n_stims_in_recording"] = rec.n_stims
        checks = integrity.check_recording(
            attributes=rec.attributes, samples=rec.samples, spike_ts=rec.spike_ts, spike_ch=rec.spike_ch,
            window_start=WINDOW_START_FRAME, window_frames=cfg.window_frames,
            non_signal_channels=layout.non_signal_channels, worker_log=worker_log,
            unexpected_env=env_unexpected,
        )
        checks.append(integrity._check(
            "worker_succeeded", worker_error is None,
            worker_error or "worker finished without error",
        ))
        fps = int(rec.attributes.get("frames_per_second", cfg.frames_per_second))
        if fps != cfg.frames_per_second:
            checks.append(integrity._check("frames_per_second", False,
                                           f"recording has {fps} fps, window was sized for {cfg.frames_per_second}"))
        manifest["integrity"] = {
            "checks": checks,
            "errors": [c["name"] for c in checks if not c["passed"] and c["severity"] == "error"],
            "warnings": [c["name"] for c in checks if not c["passed"] and c["severity"] == "warning"],
        }
        manifest["status"] = "failed" if timed_out else integrity.status_from_checks(checks)
        if rec.samples.shape[0] >= cfg.window_frames and rec.samples.ndim == 2:
            canon = canonical.canonicalize(rec.samples, rec.spike_ts, rec.spike_ch, cfg.window_frames)
            manifest["canonical"] = canonical.digests(canon)
            metrics = compute_all(
                canon.spike_ts, canon.spike_ch, n_frames=canon.n_frames, fps=fps,
                channel_count=canon.samples.shape[1], excluded_channels=layout.non_signal_channels,
                config=MetricsConfig(active_rate_threshold_hz=cfg.active_rate_threshold_hz,
                                     population_bin_ms=cfg.population_bin_ms),
            )
            metrics["status"] = manifest["status"]
            metrics["data_label"] = manifest["data_label"]
            mf.write_json(run_dir / "metrics.json", metrics)
            _write_channel_csv(run_dir / "channel_metrics.csv", metrics["channels"])
            core = {"summary": metrics["summary"], "channels": metrics["channels"]}
            manifest["metrics_sha256"] = mf.metrics_digest(core)
    except Exception as exc:  # analysis problems become a failed run, not a crash
        manifest["status"] = "failed"
        manifest["error"] = f"analysis failed: {type(exc).__name__}: {exc}"
    manifest["finished_utc"] = mf.utc_now()
    try:
        render_report(manifest, metrics, canon, layout, run_dir / "report.html")
    except Exception as exc:
        manifest.setdefault("report_error", f"{type(exc).__name__}: {exc}")
    manifest["files"] = {
        p.name: mf.file_entry(p) for p in sorted(run_dir.iterdir())
        if p.is_file() and p.name != "manifest.json"
    }
    mf.write_json(run_dir / "manifest.json", manifest)
    return manifest


def run(cfg: RunConfig, out_dir: Path, *, timeout_s: float | None = None) -> tuple[Path, dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = new_run_id(cfg.seed)
    run_dir = out_dir / run_id
    run_dir.mkdir(exist_ok=False)
    manifest: dict = {
        "schema": mf.MANIFEST_SCHEMA,
        "run_id": run_id,
        "status": "running",
        "data_label": cfg.data_label,
        "data_label_note": mf.DATA_LABEL_NOTES[cfg.data_label],
        "created_utc": mf.utc_now(),
        "finished_utc": None,
        "error": None,
        "config": cfg.to_dict(),
        "acquisition": {
            "window_start_frame": WINDOW_START_FRAME,
            "window_frames": cfg.window_frames,
            "alignment": "fresh simulator process; Neurons.record(from_timestamp=window_start); "
                         "stopped once frame window_start+window_frames exists; canonical data "
                         "trimmed to [window_start, window_start+window_frames)",
        },
        "sdk": {"cl_sdk_version": None, "env_set_by_workbench": cfg.sdk_env()},
        "environment": mf.environment_info(),
        "code": mf.code_info(),
        "integrity": None,
        "canonical": None,
        "metrics_sha256": None,
    }
    manifest["sdk"]["cl_sdk_version"] = manifest["environment"]["packages"].get("cl-sdk")
    if cfg.replay_path:
        src = Path(cfg.replay_path)
        manifest["acquisition"]["replay_source"] = {"path": str(src.resolve()), **mf.file_entry(src)}
    mf.write_json(run_dir / "manifest.json", manifest)

    try:
        result = acquire(cfg, run_dir, run_id, timeout_s=timeout_s)
    except KeyboardInterrupt as exc:
        manifest.update(status="failed", error="interrupted by user", finished_utc=mf.utc_now())
        if hasattr(exc, "process_cleanup"):  # same key as after a timeout
            manifest["acquisition"]["worker"] = {"process_cleanup": exc.process_cleanup}
        mf.write_json(run_dir / "manifest.json", manifest)
        raise
    log = result.pop("log", "")
    manifest["acquisition"]["worker"] = {k: v for k, v in result.items() if k != "traceback"}
    env_bad = unexpected_env(result.get("env_seen", {}), cfg.sdk_env()) if "env_seen" in result else {}

    rec = _find_recording(run_dir, result)
    if rec is not None:
        rec.rename(run_dir / "recording.h5")
    if rec is None:
        manifest.update(status="failed", error=result.get("error") or "no recording file produced",
                        finished_utc=mf.utc_now())
        from .report import render_report
        render_report(manifest, None, None, None, run_dir / "report.html")
        manifest["files"] = {p.name: mf.file_entry(p) for p in sorted(run_dir.iterdir())
                             if p.is_file() and p.name != "manifest.json"}
        mf.write_json(run_dir / "manifest.json", manifest)
        return run_dir, manifest
    worker_error = None if result.get("ok") else (result.get("error") or "worker failed")
    if worker_error:
        manifest["error"] = worker_error
    manifest = finalize(run_dir, manifest, worker_log=log, env_unexpected=env_bad, cfg=cfg,
                        worker_error=worker_error, timed_out=bool(result.get("timed_out")))
    return run_dir, manifest
