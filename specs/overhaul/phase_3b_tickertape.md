# Phase 3b — Tickertape Scraper (MF / Sector / Beta)

```yaml
phase_id: phase_3b
status: pending
depends_on: []
blocks: [phase_1_smart_money_pillar, phase_5_pead]
estimated_effort: 3 days
test_framework: pytest + responses (HTTP mocking)
```

## Goal

The Smart Money pillar (Phase 1) is starved because `src/plutus/data/smart_money.py:8–39` returns a hardcoded `UNKNOWN` for MF data. Tickertape's public stock pages expose: (1) MF holding delta over 2 months, (2) sector classification, (3) trailing beta vs Nifty 1Y, (4) upcoming earnings date (PEAD prerequisite). This phase ships a polite, throttled scraper + 24h on-disk cache.

## Acceptance criteria

- [ ] `get_mf_holdings_delta(symbol)` returns `{verdict, mf_count_accumulating, mf_count_reducing, last_updated}` from Tickertape, or `UNKNOWN` if fetch fails (graceful)
- [ ] `get_sector(symbol)` returns the GICS-style sector (e.g., `"IT Services"`, `"Banking"`)
- [ ] `get_beta(symbol)` returns 1Y trailing beta vs Nifty as float
- [ ] `get_next_earnings_date(symbol)` returns ISO date or None
- [ ] Scraper respects 1 req/sec, polite User-Agent, exponential backoff on 429
- [ ] 24h on-disk cache; no live fetch within TTL
- [ ] All four `UNKNOWN` cases in `src/plutus/data/smart_money.py:8–39` replaced by real Tickertape calls

## Prerequisites

None.

## Task list

### TASK-3b.1 — Schema: `sector_metadata` + `institutional_flows`

```yaml
parallelizable: no
parallel_group: null
reason: All other tasks persist to these tables.
estimated_effort: 30min
```

**Test first**:
```python
def test_sector_metadata_persists(db_session):
    from plutus.db.models import SectorMetadata
    sm = SectorMetadata(symbol="RELIANCE", sector="Energy", beta=1.05, last_refreshed=datetime.utcnow())
    db_session.add(sm); db_session.commit()
    assert db_session.query(SectorMetadata).filter_by(symbol="RELIANCE").one().sector == "Energy"

def test_institutional_flows_persists(db_session):
    from plutus.db.models import InstitutionalFlow
    f = InstitutionalFlow(flow_date=date.today(), fii_net_cr=1500.0, dii_net_cr=2300.0)
    db_session.add(f); db_session.commit()
```

**Files to modify**:
- `src/plutus/db/models.py` — `SectorMetadata`, `InstitutionalFlow`.
- `migrations/00X_phase3b_tickertape.sql`.

**Acceptance**: migration + tests green.

---

### TASK-3b.2 — HTTP client with throttle + cache + backoff

```yaml
parallelizable: no
parallel_group: null
reason: All scraper functions depend on this client.
estimated_effort: 4h
```

**Test first** (use the `responses` library to mock HTTP):
```python
# tests/test_tickertape/test_client.py
import responses
from plutus.data.tickertape import TickertapeClient

@responses.activate
def test_polite_user_agent_sent():
    responses.add(responses.GET, "https://www.tickertape.in/stocks/reliance-industries-RELI",
                  json={"name": "Reliance"}, status=200)
    client = TickertapeClient()
    client.fetch_stock_page("RELI")
    assert "Plutus" in responses.calls[0].request.headers["User-Agent"]

@responses.activate
def test_throttle_1_req_per_sec(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda x: sleep_calls.append(x))
    responses.add(responses.GET, "https://...", json={}, status=200)
    client = TickertapeClient()
    client.fetch_stock_page("A")
    client.fetch_stock_page("B")
    assert any(s >= 1.0 for s in sleep_calls)

@responses.activate
def test_429_triggers_backoff(monkeypatch):
    responses.add(responses.GET, "https://...", status=429)
    responses.add(responses.GET, "https://...", json={}, status=200)
    client = TickertapeClient()
    result = client.fetch_stock_page("A")
    assert result == {}   # second call succeeds

@responses.activate
def test_cache_hit_does_not_fetch(tmp_path):
    cache = tmp_path / "tt.json"
    cache.write_text(json.dumps({"RELI": {"data": "...", "fetched_at": "<now>"}}))
    client = TickertapeClient(cache_path=cache)
    client.fetch_stock_page("RELI")
    assert len(responses.calls) == 0
```

**Files to create**:
- `src/plutus/data/tickertape.py` — `TickertapeClient` class.

**Acceptance**: 4 tests green.

---

### Parallel group 3B — Per-field extractors (TASK-3b.3 through TASK-3b.6)

Each extractor parses a different field from the same cached page. Independent.

### TASK-3b.3 — `get_mf_holdings_delta(symbol)`

```yaml
parallelizable: yes
parallel_group: 3B
estimated_effort: 3h
```

**Test first**:
```python
def test_parse_mf_accumulating(tickertape_page_fixture):
    delta = parse_mf_delta(tickertape_page_fixture("RELIANCE_mf_acc.html"))
    assert delta["verdict"] == "ACCUMULATING"
    assert delta["mf_count_accumulating"] >= 2

def test_parse_mf_reducing(tickertape_page_fixture):
    delta = parse_mf_delta(tickertape_page_fixture("XYZ_mf_red.html"))
    assert delta["verdict"] == "REDUCING"

def test_parse_missing_section_returns_unknown(tickertape_page_fixture):
    delta = parse_mf_delta("<html></html>")
    assert delta["verdict"] == "UNKNOWN"
```

**Files**: extend `src/plutus/data/tickertape.py`.

**Acceptance**: tests green. Replaces `src/plutus/data/smart_money.py:8–39` `UNKNOWN` path.

---

### TASK-3b.4 — `get_sector(symbol)`

```yaml
parallelizable: yes
parallel_group: 3B
estimated_effort: 1h
```

**Test first**:
```python
def test_get_sector_reliance(): assert get_sector("RELIANCE") == "Energy"
def test_get_sector_unknown_ticker(): assert get_sector("ZZZZZ") is None
```

**Acceptance**: tests green; `seed_universe_v2.csv` enriched.

---

### TASK-3b.5 — `get_beta(symbol)`

```yaml
parallelizable: yes
parallel_group: 3B
estimated_effort: 1h
```

**Test first**:
```python
def test_get_beta_large_cap_near_1():
    assert 0.7 <= get_beta("HDFCBANK") <= 1.4

def test_get_beta_high_beta_stock():
    # IT mid-caps typically have beta > 1.2
    ...
```

---

### TASK-3b.6 — `get_next_earnings_date(symbol)`

```yaml
parallelizable: yes
parallel_group: 3B
estimated_effort: 2h
```

**Test first**:
```python
def test_get_earnings_returns_iso_date():
    d = get_next_earnings_date("RELIANCE")
    assert d is None or isinstance(d, date)

def test_get_earnings_window_indian_season():
    # July-Aug for Q1, Oct-Nov for Q2, etc.
    d = get_next_earnings_date("INFY")
    if d:
        assert d.month in {1, 4, 7, 10, 11}
```

**Note**: this feeds Phase 5 (PEAD bundle).

---

### TASK-3b.7 — Replace `UNKNOWN` in `smart_money.py`

```yaml
parallelizable: no
parallel_group: null
reason: Sequential after TASK-3b.3.
estimated_effort: 1h
```

**Test first**:
```python
def test_smart_money_uses_tickertape(monkeypatch):
    monkeypatch.setattr("plutus.data.tickertape.get_mf_holdings_delta",
                        lambda s: {"verdict": "ACCUMULATING", ...})
    result = get_mf_signal("RELIANCE")
    assert result["verdict"] == "ACCUMULATING"

def test_smart_money_falls_back_gracefully(monkeypatch):
    monkeypatch.setattr("plutus.data.tickertape.get_mf_holdings_delta",
                        lambda s: (_ for _ in ()).throw(Exception("network")))
    result = get_mf_signal("RELIANCE")
    assert result["verdict"] == "UNKNOWN"
```

**Files to modify**:
- `src/plutus/data/smart_money.py:8–39` — delete the hardcoded `UNKNOWN` path; route through Tickertape with graceful fallback.

**Acceptance**: both tests green.

## Streamlit considerations

None directly. Sector + beta surface in dashboard (`phase_dashboard.md`).

## Verification

```bash
pytest tests/test_tickertape/ -v
python -c "
from plutus.data.tickertape import get_mf_holdings_delta, get_sector, get_beta
print(get_mf_holdings_delta('RELIANCE'))
print(get_sector('RELIANCE'))
print(get_beta('RELIANCE'))
"
```

## Done definition

- [ ] All 7 tasks complete
- [ ] All tests green
- [ ] Manual run hits real Tickertape ≤ 4 times (one per field), respects throttle
- [ ] Phase 1 SmartMoney pillar unblocked

## References

- Plan: Phase 3 section
- Code anchors:
  - `src/plutus/data/smart_money.py:8–39` — old hardcoded UNKNOWN (to delete)
- Tickertape stock page format: `https://www.tickertape.in/stocks/<slug>-<ticker>`
