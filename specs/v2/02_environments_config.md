# 02 — Environments & Configuration

> One `.env`. One `Settings` class. Every tunable here. Resolves review A6 (2% vs 5% contradiction).

---

## 1. Files

```
plutus-app/.env            # gitignored, real secrets
plutus-app/.env.example    # committed, documents every key
src/plutus/config/settings.py
src/plutus/config/logging.py
```

No per-environment `.env.dev`/`.env.prod` files. The same `Settings` class loads from env; deployment overrides via environment variables (Docker, systemd, k8s). Profiles (dev/prod) live as code paths inside `Settings`, not as separate files.

---

## 2. `Settings` class (Pydantic v2)

```python
class Settings(BaseSettings):
    # --- runtime ---
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- database ---
    db_url: str = "sqlite:///./plutus.db"           # prod: postgres URL via env

    # --- risk (resolves A6) ---
    risk_per_trade_pct: float = 0.01                 # SINGLE source of truth
    max_concurrent_swing_positions: int = 10
    max_position_pct_of_adv: float = 0.10            # B5
    sector_cap_count: int = 3                        # B3
    sector_cap_pct_of_pool: float = 0.30             # B3
    pairwise_correlation_max: float = 0.70           # B3
    drawdown_governor_trigger_pct: float = 0.07      # B4
    drawdown_governor_halving_factor: float = 0.5

    # --- universe (A17) ---
    universe_liquidity_floor_inr: int = 50_000_000   # ₹ median traded value, 20d
    universe_min_history_days: int = 252

    # --- cost model (B1) ---
    stt_pct: float = 0.001
    brokerage_per_order_inr: float = 20.0
    exchange_pct: float = 0.0000345
    gst_pct: float = 0.18                             # on brokerage+exchange
    stamp_duty_pct: float = 0.00003
    slippage_bps_base: float = 5.0                    # multiplied by position/ADV and ATR pct

    # --- expectancy gate (A4) ---
    expectancy_floor_R: float = 0.3
    drawn_rr_fallback_floor: float = 1.5

    # --- regime ---
    breadth_window_short: int = 50
    breadth_window_long: int = 200
    vix_bull_max: float = 18.0
    vix_bear_min: float = 22.0

    # --- calibration (A14) ---
    sprt_alpha: float = 0.05
    sprt_beta: float = 0.20
    calibration_min_n_low: int = 20
    calibration_min_n_high: int = 50
    soft_dead_zone_lower: int = 67
    soft_dead_zone_upper: int = 73

    # --- sentiment (A8) ---
    sentiment_pillar_weight: float = 0.05
    sentiment_hard_kill_requires_corroboration: bool = True

    # --- data providers ---
    provider_primary_ohlcv: Literal["yfinance", "nse", "tickertape"] = "yfinance"
    provider_fallback_ohlcv: Literal["nse", "tickertape", "none"] = "nse"
    cache_ttl_ohlcv_hours: int = 6
    freshness_assert_enabled: bool = True            # B11

    # --- secrets ---
    openrouter_api_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    whatsapp_api_key: SecretStr | None = None
    newsapi_key: SecretStr | None = None

    # --- scheduler ---
    sunday_full_run_hour_ist: int = 19
    monday_revalidation_hour_ist: int = 9
    monday_revalidation_minute_ist: int = 10
    midweek_mini_screen_enabled: bool = False        # B18, P3
    daily_exit_monitor_minutes: list[int] = Field(default_factory=lambda: [930, 1015, 1100, 1330, 1500])

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Every module imports `get_settings()`.** No `os.environ` reads outside `config/`.

---

## 3. Profiles

| Field | dev default | prod override (via env) |
|---|---|---|
| `db_url` | `sqlite:///./plutus.db` | `DB_URL=postgresql+psycopg://...` |
| `log_level` | `INFO` | `LOG_LEVEL=WARNING` |
| `midweek_mini_screen_enabled` | `False` | `MIDWEEK_MINI_SCREEN_ENABLED=true` once B18 ships |

---

## 4. Validation rules (binding)

The `Settings` class includes Pydantic field validators that **fail on construction** if:

- `risk_per_trade_pct > 0.02` and `environment == "prod"` (defensive — reviewer recommended 1–2%).
- `expectancy_floor_R <= 0` (a non-positive floor disables A4).
- `sector_cap_pct_of_pool > 1.0` or any `*_pct` field outside `[0, 1]`.
- `db_url.startswith("sqlite")` and `environment == "prod"` (hard error).
- `freshness_assert_enabled is False` and `environment == "prod"` (hard error — B11 must be on in prod).

---

## 5. Tests (`tests/config/test_settings.py`)

| Test | Assertion |
|---|---|
| `test_defaults_load` | `Settings()` constructs without env file. |
| `test_env_file_overrides_defaults` | Writing `RISK_PER_TRADE_PCT=0.005` in `.env` overrides default. |
| `test_prod_rejects_sqlite` | `environment=prod` + sqlite URL raises `ValidationError`. |
| `test_prod_rejects_freshness_off` | `environment=prod` + `FRESHNESS_ASSERT_ENABLED=false` raises. |
| `test_risk_above_2pct_rejected_in_prod` | `risk_per_trade_pct=0.03` + prod raises. |
| `test_secret_not_logged` | `repr(settings)` does not contain raw token string. |
| `test_no_magic_numbers_in_swing` | Static check: `ripgrep` `0\.0[125]\b` in `src/plutus/swing/` returns empty. |
| `test_a6_resolution` | Only one place in code defines per-trade risk: `risk_per_trade_pct`. Verified by AST walk for `* 0.01`, `* 0.02`, `* 0.05` constants in `swing/sizing/`. |
| `test_get_settings_cached` | Two calls return same instance. |

---

## 6. `.env.example` (committed)

```
ENVIRONMENT=dev
LOG_LEVEL=INFO
DB_URL=sqlite:///./plutus.db
RISK_PER_TRADE_PCT=0.01
OPENROUTER_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
NEWSAPI_KEY=
# see src/plutus/config/settings.py for full key list
```

---

## Acceptance criteria

- [ ] Single `.env` at repo root; `src/.env` deleted.
- [ ] `get_settings()` cached; called everywhere.
- [ ] All tests in §5 pass.
- [ ] A6 audit: only `settings.risk_per_trade_pct` controls per-trade risk.
- [ ] `import-linter` rule: nothing in `swing/`, `accumulation/`, `shared/` reads `os.environ` directly.
