"""Child process that talks to the cl-sdk simulator. Run as: python -m workbench._worker CONFIG_JSON

It runs in a fresh process so the simulator starts at device frame 0 with only the
CL_SDK_* variables the parent set (see config.RunConfig.sdk_env). It writes the
recording and a small JSON result next to the config, and nothing else.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path


def main(config_path: str) -> int:
    cfg = json.loads(Path(config_path).read_text())
    run_dir = Path(cfg["run_dir"])
    window_start = int(cfg["window_start_frame"])
    window_frames = int(cfg["window_frames"])
    result: dict = {"ok": False}
    result_path = run_dir / "worker_result.json"
    try:
        import cl  # imported here so the parent's environment is already in place

        result["env_seen"] = {k: v for k, v in sorted(os.environ.items()) if k.startswith("CL_SDK_")}
        result["is_simulator"] = bool(cl.is_simulator())
        with cl.open() as neurons:
            result["timestamp_at_open"] = int(neurons.timestamp())
            result["channel_count"] = int(neurons.get_channel_count())
            result["frames_per_second"] = int(neurons.get_frames_per_second())
            t0 = time.monotonic()
            recording = neurons.record(
                from_timestamp=window_start,
                file_location=str(run_dir),
                file_suffix="raw",
                attributes={"workbench_run_id": cfg["run_id"], "workbench_data_label": cfg["data_label"]},
            )
            result["timestamp_at_record_call"] = int(neurons.timestamp())
            # Block until the frame after the window exists, then stop. stop_after_* is not
            # used: with from_timestamp in the past it counts from the call time, not the window start.
            neurons.read(1, window_start + window_frames)
            recording.stop()
            result["timestamp_at_stop"] = int(neurons.timestamp())
            result["record_wall_seconds"] = round(time.monotonic() - t0, 3)
        result["recording_path"] = str(recording.file["path"])
        result["ok"] = True
        code = 0
    except BaseException as exc:  # keep a record of every failure, including Ctrl-C
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
        code = 1
    result_path.write_text(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
