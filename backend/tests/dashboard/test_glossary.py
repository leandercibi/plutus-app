from __future__ import annotations

from tests.dashboard.helpers import run_window


def test_glossary_renders_without_error() -> None:
    at = run_window("glossary", None)
    assert not at.exception


def test_glossary_shows_search_box() -> None:
    at = run_window("glossary", None)
    assert any("glossary_search" in ti.key for ti in at.text_input)


def test_glossary_all_terms_present_by_default() -> None:
    at = run_window("glossary", None)
    md = " ".join(m.value for m in at.markdown)
    # spot-check a few term names that are in expander labels (also in markdown badges)
    assert "RS Blend" in md or any("RS Blend" in e.label for e in at.expander)


def test_glossary_rs_blend_term_exists() -> None:
    at = run_window("glossary", None)
    expander_labels = [e.label for e in at.expander]
    assert any("RS Blend" in lbl for lbl in expander_labels)


def test_glossary_hard_avoid_term_exists() -> None:
    at = run_window("glossary", None)
    expander_labels = [e.label for e in at.expander]
    assert any("Hard Avoid" in lbl for lbl in expander_labels)


def test_glossary_tranche_term_exists() -> None:
    at = run_window("glossary", None)
    expander_labels = [e.label for e in at.expander]
    assert any("Tranche" in lbl for lbl in expander_labels)


def test_glossary_category_selectbox_present() -> None:
    at = run_window("glossary", None)
    selectbox_keys = {s.key for s in at.selectbox}
    assert "glossary_cat" in selectbox_keys


def test_glossary_covers_all_categories() -> None:
    from plutus.dashboard.windows.glossary import _TERMS

    categories = {t["category"] for t in _TERMS}
    assert "accumulation" in categories
    assert "swing" in categories
    assert "market" in categories
    assert "backtesting" in categories
    assert "calibration" in categories


def test_glossary_terms_have_required_fields() -> None:
    from plutus.dashboard.windows.glossary import _TERMS

    required = {"name", "category", "one_liner", "detail", "analogy", "how_to_use"}
    for term in _TERMS:
        missing = required - term.keys()
        assert not missing, f"Term '{term.get('name')}' missing fields: {missing}"


def test_glossary_minimum_term_count() -> None:
    from plutus.dashboard.windows.glossary import _TERMS

    assert len(_TERMS) >= 20, f"Expected at least 20 terms, got {len(_TERMS)}"
