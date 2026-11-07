"""Run configuration and the exact CL_SDK_* environment it maps to."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

# Documented cl-sdk 1.0.0 defaults (README "User Options"), set explicitly so a stray
# .env file cannot change them silently.
SDK_DEFAULT_SAMPLE_MEAN = 170
SDK_DEFAULT_SPIKE_PERCENTILE = 99.995
WINDOW_START_FRAME = 0  # each run starts in a fresh process, at device frame 0


@dataclass(frozen=True)
class RunConfig:
    seconds: float = 5.0
    seed: int = 42
    start_offset: int = 0
    accelerated: bool = False
    replay_path: str | None = None
    sample_mean: int = SDK_DEFAULT_SAMPLE_MEAN
    spike_percentile: float = SDK_DEFAULT_SPIKE_PERCENTILE
    frames_per_second: int = 25_000  # used to size the window; checked against the recording
    population_bin_ms: float = 100.0
    active_rate_threshold_hz: float = 0.1
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.seconds <= 0:
            raise ValueError("seconds must be positive")
        if self.start_offset < 0:
            raise ValueError("start_offset must be >= 0")

    @property
    def window_frames(self) -> int:
        return int(round(self.seconds * self.frames_per_second))

    @property
    def timing_mode(self) -> str:
        return "accelerated" if self.accelerated else "wall_clock"

    @property
    def data_label(self) -> str:
        return "REPLAYED" if self.replay_path else "SYNTHETIC"

    def sdk_env(self) -> dict[str, str]:
        """The complete set of CL_SDK_* variables the child process gets."""
        env = {
            "CL_SDK_RANDOM_SEED": str(self.seed),
            "CL_SDK_REPLAY_START_OFFSET": str(self.start_offset),
            "CL_SDK_ACCELERATED_TIME": "1" if self.accelerated else "0",
            "CL_SDK_VISUALISATION": "0",  # never start the local WebSocket server
            "CL_SDK_SAMPLE_MEAN": str(self.sample_mean),
            "CL_SDK_SPIKE_PERCENTILE": repr(float(self.spike_percentile)),
            "CL_SDK_SPIKE_VISIBILITY": "0",
        }
        if self.replay_path:
            env["CL_SDK_REPLAY_PATH"] = str(Path(self.replay_path).resolve())
        return env

    def to_dict(self) -> dict:
        d = asdict(self)
        d["window_frames"] = self.window_frames
        d["window_start_frame"] = WINDOW_START_FRAME
        d["timing_mode"] = self.timing_mode
        d["data_label"] = self.data_label
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RunConfig":
        keys = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in keys})
