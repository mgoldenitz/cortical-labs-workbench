"""Command line: workbench run | verify | compare."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import RunConfig


def _cmd_run(args) -> int:
    from .pipeline import run

    cfg = RunConfig(
        seconds=args.seconds, seed=args.seed, start_offset=args.start_offset,
        accelerated=args.accelerated, replay_path=args.replay,
        population_bin_ms=args.bin_ms, active_rate_threshold_hz=args.active_hz,
    )
    if cfg.accelerated:
        print("note: accelerated mode lost data in one 10 s test on 2026-11-06; the integrity "
              "checks will mark the run incomplete if that happens.", file=sys.stderr)
    run_dir, manifest = run(cfg, Path(args.out))
    print(f"run:    {run_dir}")
    print(f"status: {manifest['status'].upper()}  ({manifest['data_label']} data)")
    if manifest.get("error"):
        print(f"error:  {manifest['error']}")
    integ = manifest.get("integrity") or {}
    if integ.get("errors"):
        print(f"failed checks:   {', '.join(integ['errors'])}")
    if integ.get("warnings"):
        print(f"warnings:        {', '.join(integ['warnings'])}")
    canon = manifest.get("canonical") or {}
    if canon:
        print(f"samples sha256:  {canon['samples_sha256']}")
        print(f"spikes sha256:   {canon['spikes_sha256']}  ({canon['n_spikes']} spikes)")
    print(f"report: {run_dir / 'report.html'}")
    return 0 if manifest["status"] == "complete" else 2


def _cmd_verify(args) -> int:
    from . import canonical, manifest as mf
    from .recording_io import load_recording

    run_dir = Path(args.run_dir)
    m = json.loads((run_dir / "manifest.json").read_text())
    problems = []
    for name, entry in (m.get("files") or {}).items():
        p = run_dir / name
        if not p.exists():
            problems.append(f"missing file {name}")
        elif mf.sha256_file(p) != entry["sha256"]:
            problems.append(f"checksum mismatch: {name}")
    if m.get("canonical") and (run_dir / "recording.h5").exists():
        rec = load_recording(run_dir / "recording.h5")
        canon = canonical.canonicalize(rec.samples, rec.spike_ts, rec.spike_ch, m["canonical"]["window_frames"])
        d = canonical.digests(canon)
        for k in ("samples_sha256", "spikes_sha256", "n_spikes"):
            if d[k] != m["canonical"][k]:
                problems.append(f"canonical {k} differs from manifest")
    print(f"status recorded in manifest: {m.get('status')}")
    if problems:
        print("VERIFY FAILED:\n  " + "\n  ".join(problems))
        return 1
    print("verify OK: file checksums and canonical digests match the manifest")
    return 0


def _cmd_compare(args) -> int:
    from .metrics import compare_metrics

    a, b = Path(args.run_a), Path(args.run_b)
    ma = json.loads((a / "manifest.json").read_text())
    mb = json.loads((b / "manifest.json").read_text())
    out, same = [], True
    for m, name in ((ma, a.name), (mb, b.name)):
        if m.get("status") != "complete":
            out.append(f"warning: {name} status is {m.get('status')}")
    ca, cb = ma.get("canonical") or {}, mb.get("canonical") or {}
    for k in ("window_frames", "n_channels", "n_spikes", "samples_sha256", "spikes_sha256"):
        eq = ca.get(k) == cb.get(k)
        same &= eq
        out.append(f"{'same' if eq else 'DIFF'}  {k}")
    ka = {k: ma["config"].get(k) for k in ("seed", "start_offset", "seconds", "timing_mode", "replay_path")}
    kb = {k: mb["config"].get(k) for k in ka}
    if ka != kb:
        out.append(f"settings differ: {ka} vs {kb}")
    if (a / "metrics.json").exists() and (b / "metrics.json").exists():
        xa = json.loads((a / "metrics.json").read_text())
        xb = json.loads((b / "metrics.json").read_text())
        diffs = compare_metrics({"summary": xa["summary"], "channels": xa["channels"]},
                                {"summary": xb["summary"], "channels": xb["channels"]})
        same &= not diffs
        out.append("same  metrics (all values)" if not diffs else f"DIFF  metrics: {len(diffs)} values differ")
        out.extend(f"      {d}" for d in diffs[: args.max_diffs])
    else:
        same = False
        out.append("DIFF  metrics: missing metrics.json in one run")
    print("\n".join(out))
    print("RESULT: identical canonical data and metrics" if same else "RESULT: runs differ")
    return 0 if same else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="workbench", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="record one simulator session and write a report")
    r.add_argument("--seconds", type=float, default=5.0, help="window length in seconds (default 5)")
    r.add_argument("--seed", type=int, default=42, help="CL_SDK_RANDOM_SEED (default 42)")
    r.add_argument("--start-offset", type=int, default=0,
                   help="CL_SDK_REPLAY_START_OFFSET in frames (default 0)")
    r.add_argument("--accelerated", action="store_true",
                   help="use accelerated simulator time (default: wall clock)")
    r.add_argument("--replay", metavar="H5", help="replay this HDF5 recording instead of random data")
    r.add_argument("--bin-ms", type=float, default=100.0, help="population-rate bin width (ms)")
    r.add_argument("--active-hz", type=float, default=0.1, help="active-channel rate threshold (Hz)")
    r.add_argument("--out", default="runs", help="parent folder for run folders (default ./runs)")
    r.set_defaults(func=_cmd_run)

    v = sub.add_parser("verify", help="re-check a run folder against its manifest")
    v.add_argument("run_dir")
    v.set_defaults(func=_cmd_verify)

    c = sub.add_parser("compare", help="compare canonical data and metrics of two runs")
    c.add_argument("run_a")
    c.add_argument("run_b")
    c.add_argument("--max-diffs", type=int, default=20)
    c.set_defaults(func=_cmd_compare)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
