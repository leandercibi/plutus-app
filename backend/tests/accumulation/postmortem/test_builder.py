from __future__ import annotations

from datetime import date

from plutus.accumulation.postmortem.builder import (
    AccumulationPostmortemInputs,
    PausedPosition,
    PositionThesisStatus,
    build_accumulation_postmortem_md,
)


def _inputs() -> AccumulationPostmortemInputs:
    return AccumulationPostmortemInputs(
        week_ending=date(2024, 6, 7),
        positions=[
            PositionThesisStatus(
                symbol="TCS",
                state="BUILDING",
                thesis_intact=True,
                rs_30=0.05,
                rs_90=0.08,
                rs_180=0.11,
                tranches_filled=2,
                tranches_total=5,
            ),
            PositionThesisStatus(
                symbol="HDFCBANK",
                state="FULL",
                thesis_intact=True,
                rs_30=0.02,
                rs_90=0.04,
                rs_180=0.06,
                tranches_filled=5,
                tranches_total=5,
            ),
        ],
        paused=[
            PausedPosition(symbol="YESBANK", reason="quality pillar dropped 14 points"),
        ],
    )


def test_renders_required_sections() -> None:
    md = build_accumulation_postmortem_md(_inputs())
    assert "Accumulation postmortem" in md
    assert "TCS" in md
    assert "HDFCBANK" in md
    # RS blend movement present
    assert "RS 30/90/180" in md
    # tranche fill summary present
    assert "2/5" in md


def test_paused_list_with_reasons() -> None:
    md = build_accumulation_postmortem_md(_inputs())
    assert "Paused" in md
    assert "YESBANK" in md
    assert "quality pillar dropped 14 points" in md


def test_empty_paused_list_renders_none() -> None:
    inputs = AccumulationPostmortemInputs(
        week_ending=date(2024, 6, 7), positions=[], paused=[]
    )
    md = build_accumulation_postmortem_md(inputs)
    assert "Paused" in md
    assert "none" in md.lower()
