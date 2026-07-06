from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class PositionThesisStatus:
    symbol: str
    state: str
    thesis_intact: bool
    rs_30: float
    rs_90: float
    rs_180: float
    tranches_filled: int
    tranches_total: int


@dataclass(frozen=True)
class PausedPosition:
    symbol: str
    reason: str


@dataclass(frozen=True)
class AccumulationPostmortemInputs:
    week_ending: date
    positions: list[PositionThesisStatus] = field(default_factory=list)
    paused: list[PausedPosition] = field(default_factory=list)


def build_accumulation_postmortem_md(inputs: AccumulationPostmortemInputs) -> str:
    """Spec 08 §9 — weekly accumulation postmortem markdown.

    Sections: per-position thesis status, RS blend movement, tranche fill summary,
    and a paused list with reasons.
    """
    lines: list[str] = []
    lines.append(f"# Accumulation postmortem — {inputs.week_ending.isoformat()}")
    lines.append("")
    lines.append("## Positions")
    if inputs.positions:
        lines.append("| symbol | state | thesis | RS 30/90/180 | tranches |")
        lines.append("|---|---|---|---|---|")
        for p in inputs.positions:
            thesis = "intact" if p.thesis_intact else "broken"
            rs = f"{p.rs_30:.0%}/{p.rs_90:.0%}/{p.rs_180:.0%}"
            tranches = f"{p.tranches_filled}/{p.tranches_total}"
            lines.append(f"| {p.symbol} | {p.state} | {thesis} | {rs} | {tranches} |")
    else:
        lines.append("none")
    lines.append("")
    lines.append("## Paused positions")
    if inputs.paused:
        for paused in inputs.paused:
            lines.append(f"- {paused.symbol}: {paused.reason}")
    else:
        lines.append("none")
    lines.append("")
    return "\n".join(lines)
