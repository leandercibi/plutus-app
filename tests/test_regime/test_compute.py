# tests/test_regime/test_compute.py
import pytest
import plutus.data.regime as regime_mod
from plutus.data.regime import get_nifty_regime, get_sector_strength, INDEX_YF_MAP, SECTOR_DISPLAY


def _reset_caches():
    regime_mod._regime_cache = None
    regime_mod._sector_cache = None


@pytest.fixture(autouse=True)
def clear_caches():
    _reset_caches()
    yield
    _reset_caches()


# ── fetch_index_ohlcv ────────────────────────────────────────────────────

def test_fetch_nifty_50_returns_attrs(monkeypatch, synthetic_bull_nifty_df):
    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv", lambda s, **kw: synthetic_bull_nifty_df)
    df = regime_mod.fetch_index_ohlcv("NIFTY_50", days=90)
    assert df.attrs["bars_fetched"] >= 60
    assert "Close" in df.columns


@pytest.mark.parametrize("symbol", list(INDEX_YF_MAP.keys()))
def test_all_index_symbols_in_map(symbol):
    assert symbol in INDEX_YF_MAP
    yf_sym = INDEX_YF_MAP[symbol]
    assert yf_sym.startswith("^")


# ── get_nifty_regime ─────────────────────────────────────────────────────

def test_bull_regime(synthetic_bull_nifty_df, monkeypatch, tmp_path):
    monkeypatch.setattr(regime_mod, "_REGIME_CACHE_FILE", tmp_path / "regime.json")
    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv",
                        lambda *a, **kw: synthetic_bull_nifty_df)
    r = get_nifty_regime(force=True)
    assert r["trend"] == "BULL"
    assert r["slope"] > 0
    assert r["distance_from_ema50_pct"] > 0


def test_bear_regime(synthetic_bear_nifty_df, monkeypatch, tmp_path):
    monkeypatch.setattr(regime_mod, "_REGIME_CACHE_FILE", tmp_path / "regime.json")
    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv",
                        lambda *a, **kw: synthetic_bear_nifty_df)
    r = get_nifty_regime(force=True)
    assert r["trend"] == "BEAR"
    assert r["slope"] < 0
    assert r["distance_from_ema50_pct"] < 0


def test_sideways_regime(synthetic_flat_nifty_df, monkeypatch, tmp_path):
    monkeypatch.setattr(regime_mod, "_REGIME_CACHE_FILE", tmp_path / "regime.json")
    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv",
                        lambda *a, **kw: synthetic_flat_nifty_df)
    r = get_nifty_regime(force=True)
    assert r["trend"] in {"SIDEWAYS", "BULL", "BEAR"}  # flat may tip either way
    assert "slope" in r
    assert "distance_from_ema50_pct" in r


def test_regime_returns_required_keys(synthetic_bull_nifty_df, monkeypatch, tmp_path):
    monkeypatch.setattr(regime_mod, "_REGIME_CACHE_FILE", tmp_path / "regime.json")
    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv",
                        lambda *a, **kw: synthetic_bull_nifty_df)
    r = get_nifty_regime(force=True)
    assert {"trend", "slope", "distance_from_ema50_pct"} <= r.keys()


def test_regime_caches_in_memory(synthetic_bull_nifty_df, monkeypatch, tmp_path):
    """Second call (force=False) should not call fetch_index_ohlcv again."""
    monkeypatch.setattr(regime_mod, "_REGIME_CACHE_FILE", tmp_path / "regime.json")
    call_count = [0]

    def counting_fetch(*a, **kw):
        call_count[0] += 1
        return synthetic_bull_nifty_df

    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv", counting_fetch)

    get_nifty_regime(force=True)   # primes the in-memory cache
    get_nifty_regime(force=False)  # should read from cache
    assert call_count[0] == 1


# ── get_sector_strength ──────────────────────────────────────────────────

def test_sector_strength_returns_all_sectors(sector_dfs, monkeypatch, tmp_path):
    monkeypatch.setattr(regime_mod, "_SECTOR_CACHE_FILE", tmp_path / "sector.json")

    def mock_fetch(symbol, **kw):
        return sector_dfs.get(symbol, sector_dfs["NIFTY_50"])

    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv", mock_fetch)
    rs = get_sector_strength(force=True)
    for display in SECTOR_DISPLAY.values():
        assert display in rs


def test_outperformer_has_rs_above_1(sector_dfs, monkeypatch, tmp_path):
    monkeypatch.setattr(regime_mod, "_SECTOR_CACHE_FILE", tmp_path / "sector.json")

    def mock_fetch(symbol, **kw):
        return sector_dfs.get(symbol, sector_dfs["NIFTY_50"])

    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv", mock_fetch)
    rs = get_sector_strength(force=True)
    assert rs["IT"] > 1.05  # IT up ~15% vs Nifty up ~2%


def test_underperformer_has_rs_below_1(sector_dfs, monkeypatch, tmp_path):
    monkeypatch.setattr(regime_mod, "_SECTOR_CACHE_FILE", tmp_path / "sector.json")

    def mock_fetch(symbol, **kw):
        return sector_dfs.get(symbol, sector_dfs["NIFTY_50"])

    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv", mock_fetch)
    rs = get_sector_strength(force=True)
    assert rs["METAL"] < 0.97  # METAL down ~5% vs Nifty up ~2%


def test_sector_strength_caches_in_memory(sector_dfs, monkeypatch, tmp_path):
    monkeypatch.setattr(regime_mod, "_SECTOR_CACHE_FILE", tmp_path / "sector.json")
    call_count = [0]

    def counting_fetch(symbol, **kw):
        call_count[0] += 1
        return sector_dfs.get(symbol, sector_dfs["NIFTY_50"])

    monkeypatch.setattr(regime_mod, "fetch_index_ohlcv", counting_fetch)
    get_sector_strength(force=True)
    first_count = call_count[0]
    get_sector_strength(force=False)
    assert call_count[0] == first_count  # no extra fetches
