"""Self-contained static HTML report. No external scripts, styles, fonts or images."""

from __future__ import annotations

import base64
import html
import io
from pathlib import Path

import numpy as np

from .metrics import population_rate


def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", metadata={"Software": None})
    import matplotlib.pyplot as plt

    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _figures(canon, metrics: dict, layout, fps: int, bin_ms: float) -> dict[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, accent, muted = "#1f2933", "#2b6cb0", "#9aa5b1"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": muted, "axes.labelcolor": ink,
                         "xtick.color": ink, "ytick.color": ink, "axes.spines.top": False,
                         "axes.spines.right": False})
    figs: dict[str, str] = {}
    n_frames = canon.n_frames
    duration_s = n_frames / fps

    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.scatter(canon.spike_ts / fps, canon.spike_ch, s=3, color=accent, linewidths=0)
    ax.set_xlim(0, duration_s)
    ax.set_ylim(-1, canon.samples.shape[1])
    ax.set_xlabel("time from window start (s)")
    ax.set_ylabel("channel")
    ax.set_title("Spike raster", loc="left")
    figs["raster"] = _fig_to_data_uri(fig)

    rates = {r["channel"]: r["rate_hz"] for r in metrics["channels"]}
    grid = np.array([[rates.get(c, np.nan) for c in row] for row in layout.grid], dtype=float)
    mask = np.zeros_like(grid, dtype=bool)
    for r, row in enumerate(layout.grid):
        for c, ch in enumerate(row):
            if ch in layout.non_signal_channels:
                mask[r, c] = True
    fig, ax = plt.subplots(figsize=(4.6, 4))
    shown = np.ma.array(grid, mask=mask)
    im = ax.imshow(shown, cmap="Blues", vmin=0)
    for r, row in enumerate(layout.grid):
        for c, ch in enumerate(row):
            label = f"{ch}\n" + ("GND" if ch in layout.ground_channels else
                                 "REF" if ch in layout.reference_channels else f"{grid[r, c]:.2f}")
            ax.text(c, r, label, ha="center", va="center", fontsize=6,
                    color=ink if mask[r, c] or grid[r, c] < np.nanmax(grid) * 0.6 else "white")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Firing rate by electrode (Hz)", loc="left")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Hz")
    figs["layout"] = _fig_to_data_uri(fig)

    starts, counts = population_rate(canon.spike_ts[np.isin(canon.spike_ch, [r["channel"] for r in metrics["channels"] if not r["excluded"]])],
                                     n_frames=n_frames, fps=fps, bin_ms=bin_ms)
    fig, ax = plt.subplots(figsize=(8, 2.6))
    if counts.size:
        edges = np.append(starts, starts[-1] + bin_ms / 1000.0)
        ax.stairs(counts / (bin_ms / 1000.0), edges, color=accent, linewidth=1.5)
    ax.set_xlim(0, duration_s)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("time from window start (s)")
    ax.set_ylabel("spikes/s, all signal channels")
    ax.set_title(f"Population rate ({bin_ms:g} ms bins)", loc="left")
    figs["population"] = _fig_to_data_uri(fig)

    isis = []
    for ch in range(canon.samples.shape[1]):
        ts = canon.spike_ts[canon.spike_ch == ch]
        if ts.size > 1:
            isis.append(np.diff(ts) / fps * 1000.0)
    fig, ax = plt.subplots(figsize=(8, 2.6))
    if isis:
        all_isi = np.concatenate(isis)
        all_isi = all_isi[all_isi > 0]
        bins = np.logspace(np.log10(max(all_isi.min(), 0.04)), np.log10(all_isi.max() * 1.01), 40)
        ax.hist(all_isi, bins=bins, color=accent)
        ax.set_xscale("log")
    else:
        ax.text(0.5, 0.5, "fewer than two spikes on every channel", ha="center", transform=ax.transAxes)
    ax.set_xlabel("inter-spike interval (ms, log scale)")
    ax.set_ylabel("count")
    ax.set_title("Inter-spike intervals, pooled over channels", loc="left")
    figs["isi"] = _fig_to_data_uri(fig)
    return figs


def _row(*cells, header=False) -> str:
    tag = "th" if header else "td"
    return "<tr>" + "".join(f"<{tag}>{html.escape(str(c))}</{tag}>" for c in cells) + "</tr>"


def _fmt(x, nd=3):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


CSS = """
:root{--ink:#1f2933;--muted:#616e7c;--line:#e4e7eb;--bg:#ffffff;--warn:#b7791f;--bad:#c53030;--ok:#2f855a;--note:#ebf4ff}
body{font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg);margin:0}
main{max-width:960px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:8px 0 4px}h2{font-size:16px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.banner{padding:10px 14px;border-radius:6px;margin:10px 0;font-weight:600}
.label{background:var(--note);border:1px solid #bee3f8}
.complete{background:#f0fff4;border:1px solid #9ae6b4;color:var(--ok)}
.incomplete,.failed{background:#fff5f5;border:1px solid #feb2b2;color:var(--bad)}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600}.pass{color:var(--ok)}.fail{color:var(--bad)}.warn{color:var(--warn)}
img{max-width:100%;height:auto}code{font-size:12px;word-break:break-all}.muted{color:var(--muted)}
@media (prefers-color-scheme: dark){:root{--ink:#e4e7eb;--muted:#9aa5b1;--line:#3e4c59;--bg:#1f2933;--note:#243b53}
img{background:#fff;border-radius:4px}.complete{background:#1c3b2b}.incomplete,.failed{background:#4a1f1f}}
"""


def render_report(manifest: dict, metrics: dict | None, canon, layout, out_path: Path) -> None:
    status = manifest.get("status", "unknown")
    label = manifest.get("data_label", "SYNTHETIC")
    cfg = manifest.get("config", {})
    acq = manifest.get("acquisition", {})
    sdk = manifest.get("sdk", {})
    code = manifest.get("code", {})
    canon_d = manifest.get("canonical") or {}
    parts: list[str] = []
    parts.append(f"<h1>Simulator run {html.escape(manifest.get('run_id', '?'))}</h1>")
    parts.append(
        f'<div class="banner label">{html.escape(label)} DATA. '
        f"{html.escape(manifest.get('data_label_note', ''))} "
        "Metrics below describe the simulator's output; they are not evidence about biological "
        "neurons, learning or stimulation responses.</div>"
    )
    status_text = {
        "complete": "Run status: COMPLETE. All error-level integrity checks passed.",
        "incomplete": "Run status: INCOMPLETE. At least one integrity check failed; do not use these "
                      "results. Files are kept for diagnosis.",
        "failed": "Run status: FAILED. No usable recording; see the error below.",
    }.get(status, f"Run status: {status}")
    parts.append(f'<div class="banner {html.escape(status)}">{html.escape(status_text)}</div>')
    if manifest.get("error"):
        parts.append(f"<p><strong>Error:</strong> <code>{html.escape(manifest['error'])}</code></p>")

    parts.append("<h2>Run settings</h2><table>")
    for k, v in [
        ("Seed", cfg.get("seed")), ("Start offset (frames)", cfg.get("start_offset")),
        ("Window", f"device frames [{acq.get('window_start_frame', 0)}, "
                   f"{acq.get('window_start_frame', 0) + (acq.get('window_frames') or 0)}) "
                   f"= {cfg.get('seconds')} s"),
        ("Timing mode", cfg.get("timing_mode")), ("Replay source", cfg.get("replay_path") or "none"),
        ("cl-sdk version", sdk.get("cl_sdk_version")), ("Workbench version", code.get("workbench_version")),
        ("Workbench commit", f"{code.get('git_commit') or 'unknown'}{' (uncommitted changes)' if code.get('git_dirty') else ''}"),
        ("Started (UTC)", manifest.get("created_utc")), ("Finished (UTC)", manifest.get("finished_utc")),
    ]:
        parts.append(_row(k, v))
    parts.append("</table>")

    if metrics:
        s = metrics["summary"]
        parts.append("<h2>Summary metrics</h2><table>")
        for k, v in [
            ("Duration (s)", s["duration_s"]), ("Signal channels", s["channels_included"]),
            ("Excluded channels (ground, reference)", ", ".join(map(str, s["channels_excluded"]))),
            (f"Active channels (rate >= {s['active_rate_threshold_hz']} Hz)", s["active_channels"]),
            ("Total spikes", s["total_spikes"]), ("Mean rate per channel (Hz)", _fmt(s["mean_rate_hz"])),
            ("Median rate per channel (Hz)", _fmt(s["median_rate_hz"])),
            ("Max rate per channel (Hz)", _fmt(s["max_rate_hz"])),
            (f"Population rate, mean of {s['population_bin_ms']:g} ms bins (spikes/s)", _fmt(s["population_rate_mean_hz"])),
            ("Population rate, max bin (spikes/s)", _fmt(s["population_rate_max_hz"])),
        ]:
            parts.append(_row(k, v))
        parts.append("</table>")

    if metrics is not None and canon is not None and layout is not None:
        figs = _figures(canon, metrics, layout, metrics["summary"]["frames_per_second"],
                        metrics["summary"]["population_bin_ms"])
        parts.append("<h2>Activity</h2>")
        for key, alt in [("raster", "Spike raster"), ("population", "Population rate"),
                         ("layout", "Firing rate by electrode"), ("isi", "Inter-spike intervals")]:
            parts.append(f'<p><img alt="{alt}" src="{figs[key]}"></p>')

    checks = (manifest.get("integrity") or {}).get("checks") or []
    if checks:
        parts.append("<h2>Integrity checks</h2><table>" + _row("Check", "Severity", "Result", "Detail", header=True))
        for c in checks:
            cls = "pass" if c["passed"] else ("warn" if c["severity"] == "warning" else "fail")
            parts.append(
                f"<tr><td>{html.escape(c['name'])}</td><td>{html.escape(c['severity'])}</td>"
                f'<td class="{cls}">{"pass" if c["passed"] else "FAIL"}</td><td>{html.escape(c["detail"])}</td></tr>'
            )
        parts.append("</table>")

    if canon_d:
        parts.append("<h2>Canonical data digests</h2><p class=\"muted\">Runs with the same settings "
                     "should match on these. See docs/architecture.md for the byte layout.</p><table>")
        for k in ("canonical_version", "window_frames", "n_channels", "n_spikes", "samples_sha256", "spikes_sha256"):
            parts.append(f"<tr><td>{k}</td><td><code>{html.escape(str(canon_d.get(k)))}</code></td></tr>")
        if manifest.get("metrics_sha256"):
            parts.append(f"<tr><td>metrics_sha256</td><td><code>{manifest['metrics_sha256']}</code></td></tr>")
        parts.append("</table>")

    if metrics:
        parts.append("<h2>Per-channel metrics</h2><details><summary>Show all channels</summary><table>")
        parts.append(_row("Channel", "Excluded", "Spikes", "Rate (Hz)", "ISI mean (ms)", "ISI CV", header=True))
        for r in metrics["channels"]:
            parts.append(_row(r["channel"], "yes" if r["excluded"] else "", r["spike_count"],
                              _fmt(r["rate_hz"]), _fmt(r["isi_mean_ms"], 1), _fmt(r["isi_cv"])))
        parts.append("</table></details>")

    parts.append('<p class="muted">Generated by cl-workbench. The full provenance record is '
                 "manifest.json in the same folder.</p>")
    doc = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>Simulator run {html.escape(manifest.get('run_id', ''))}</title><style>{CSS}</style></head>"
        f"<body><main>{''.join(parts)}</main></body></html>"
    )
    out_path.write_text(doc, encoding="utf-8")
