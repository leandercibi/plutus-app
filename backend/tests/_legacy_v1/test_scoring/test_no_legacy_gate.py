# tests/test_scoring/test_no_legacy_gate.py
from pathlib import Path


def test_legacy_gate_absent_from_prompts():
    src = Path("src/plutus/agents/prompts.py").read_text()
    assert "technical score >= 6 AND sentiment >= 0" not in src
    assert "BUY only when" not in src


def test_synthesizer_prompt_narrative_only():
    import importlib
    from plutus.agents import prompts

    importlib.reload(prompts)
    synth = prompts.SYNTHESIZER_PROMPT
    assert "narrative" in synth
    assert "top_3_risk_flags" in synth
    # SYNTHESIZER_PROMPT must not contain the old BUY/score fields
    assert "entry_zone" not in synth
    assert "hold_days_min" not in synth
