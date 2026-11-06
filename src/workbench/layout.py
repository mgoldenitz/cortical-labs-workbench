"""Electrode layout: the one place this project touches a private cl-sdk module.

cl-sdk 1.0.0 has no public API for the physical arrangement of its 64 channels.
The layout, ground channels and reference channel are defined in the private
module ``cl.analysis._metrics._mea_layout``. Importing it here, instead of copying
its values, keeps CC BY-NC 4.0 material out of this repository (docs/licensing.md).

Because the module is private it can change or disappear in any cl-sdk release.
``pyproject.toml`` pins cl-sdk==1.0.0, and ``load_layout`` validates what it gets
so a change fails loudly instead of producing a wrong heatmap.
"""

from __future__ import annotations

from dataclasses import dataclass

PRIVATE_MODULE = "cl.analysis._metrics._mea_layout"


class LayoutUnavailable(RuntimeError):
    """The private layout module is missing or no longer looks as expected."""


@dataclass(frozen=True)
class ElectrodeLayout:
    grid: tuple[tuple[int, ...], ...]   # grid[row][col] = channel index
    ground_channels: tuple[int, ...]
    reference_channels: tuple[int, ...]
    source: str

    @property
    def channel_count(self) -> int:
        return sum(len(row) for row in self.grid)

    @property
    def non_signal_channels(self) -> tuple[int, ...]:
        """Channels that carry no neural signal (ground plus reference)."""
        return tuple(sorted(set(self.ground_channels) | set(self.reference_channels)))

    def position(self, channel: int) -> tuple[int, int]:
        for r, row in enumerate(self.grid):
            if channel in row:
                return r, row.index(channel)
        raise KeyError(channel)


def validate_layout(grid, ground, reference) -> None:
    """Raise LayoutUnavailable unless the values form a sane square layout."""
    rows = [list(r) for r in grid]
    if not rows or any(len(r) != len(rows) for r in rows):
        raise LayoutUnavailable("layout grid is not square")
    flat = [c for r in rows for c in r]
    if sorted(flat) != list(range(len(flat))):
        raise LayoutUnavailable("layout grid is not a permutation of 0..n-1")
    for c in list(ground) + list(reference):
        if c not in flat:
            raise LayoutUnavailable(f"ground/reference channel {c} not in grid")


def load_layout() -> ElectrodeLayout:
    try:
        import importlib

        mod = importlib.import_module(PRIVATE_MODULE)
        grid = mod._COMMON_MEA_LAYOUT
        ground = mod._COMMON_GROUND_CHANNELS
        reference = mod._COMMON_REFERENCE_CHANNELS
    except (ImportError, AttributeError) as exc:  # pragma: no cover - depends on SDK version
        raise LayoutUnavailable(
            f"cannot read electrode layout from private module {PRIVATE_MODULE}: {exc}. "
            "This project is verified against cl-sdk==1.0.0 only."
        ) from exc
    validate_layout(grid, ground, reference)
    return ElectrodeLayout(
        grid=tuple(tuple(int(c) for c in row) for row in grid),
        ground_channels=tuple(int(c) for c in ground),
        reference_channels=tuple(int(c) for c in reference),
        source=PRIVATE_MODULE,
    )
