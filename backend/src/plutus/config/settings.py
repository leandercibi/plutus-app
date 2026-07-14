from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- runtime ---
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- database ---
    db_url: str = "sqlite:///./plutus.db"

    # --- portfolio ---
    total_capital_inr: int = 100_000

    # --- risk (resolves A6) ---
    risk_per_trade_pct: float = 0.01
    max_concurrent_swing_positions: int = 10
    max_position_pct_of_adv: float = 0.10
    sector_cap_count: int = 3
    sector_cap_pct_of_pool: float = 0.30
    pairwise_correlation_max: float = 0.70
    drawdown_governor_trigger_pct: float = 0.07
    drawdown_governor_halving_factor: float = 0.5
    max_portfolio_heat_R: float = 6.0
    cash_position_min_deploy_count: int = 3

    # --- universe (A17) ---
    universe_liquidity_floor_inr: int = 50_000_000
    universe_min_history_days: int = 252

    # --- cost model (B1) ---
    stt_pct: float = 0.001
    brokerage_per_order_inr: float = 20.0
    exchange_pct: float = 0.0000345
    gst_pct: float = 0.18
    stamp_duty_pct: float = 0.00003
    slippage_bps_base: float = 5.0

    # --- expectancy gate (A4) ---
    expectancy_floor_R: float = 0.3
    drawn_rr_fallback_floor: float = 1.5
    bundle_min_n: int = 20

    # --- exits (B8) ---
    no_progress_t1_threshold: float = 0.3
    no_progress_elapsed_threshold: float = 0.5
    cooldown_minutes: int = 60
    chandelier_atr_mult: float = 3.0
    chandelier_atr_period: int = 22

    # --- entries (A9, B6, B7, A15) ---
    volume_gate_delivery_mult: float = 1.3
    circuit_lookback_sessions: int = 90
    breakout_strong_atr_mult: float = 2.0
    earnings_stop_widen_atr: float = 1.0
    monday_gap_kill_atr_mult: float = 1.0

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

    # --- tuner (A14) ---
    auto_tune_enabled: bool = False

    # --- v4 selection brain (off by default; see SWING_SYSTEM_REVIEW.md §8 items #1-#3) ---
    # When True the watch + bundle scoring path adds three new factors:
    #   • stock relative-strength pillar (rs_blend vs NIFTY)         0..15
    #   • per-stock smart-money flow pillar (delivery-driven for now) 0..15
    #   • continuous regime pillar (breadth/VIX/FII)                  0..15
    # Composite budget becomes tech(30) + exp(25) + regime(15) + rs(15) + flow(15) = 100.
    # When False the legacy behaviour is preserved bit-for-bit.
    enable_v4_selection: bool = False
    # Floor below which a signal is published but flagged tradable=False (no-edge band).
    score_floor_actionable: int = 50

    # --- accumulation (A12, A13, B9) ---
    accumulation_de_max: float = 1.5
    accumulation_n_tranches: int = 5

    # --- swing fundamentals avoid-filter ---
    # Swing holds are too short (~days-weeks) for quality/growth/valuation scoring to be
    # meaningful, so fundamentals only veto trades on dangerously leveraged non-financial
    # companies rather than contributing to the 0-100 score. Mirrors accumulation_de_max.
    swing_de_max: float = 1.5

    # --- api ---
    api_token: SecretStr | None = None

    # --- data providers ---
    provider_primary_ohlcv: Literal["yfinance", "nse", "tickertape"] = "yfinance"
    provider_fallback_ohlcv: Literal["nse", "tickertape", "none"] = "nse"
    cache_ttl_ohlcv_hours: int = 6
    freshness_assert_enabled: bool = True

    # --- Angel One SmartAPI ---
    angel_api_key: str = ""
    angel_client_id: str = ""
    angel_password: str = ""
    angel_totp_secret: str = ""

    # --- llm (AI summaries) ---
    llm_model: str = "deepseek/deepseek-v4-flash"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_temperature: float = 0.4
    # Headroom matters: reasoning models (e.g. deepseek-v4-flash) spend part of
    # this budget "thinking", so too small a value truncates the visible answer.
    llm_max_tokens: int = 2500
    llm_timeout_seconds: int = 60

    # --- news (Marketaux, for signal-stock insight in AI summaries) ---
    marketaux_base_url: str = "https://api.marketaux.com/v1"
    # NSE tickers are Yahoo-style on Marketaux: e.g. RELIANCE -> RELIANCE.NS
    marketaux_symbol_suffix: str = ".NS"
    news_limit: int = 3  # free tier caps articles-per-request at 3
    news_lookback_days: int = 14
    news_max_symbols: int = 8  # how many top signals to resolve sectors for
    news_max_sectors: int = 3  # how many top sectors to fetch news for
    news_country: str = "in"  # ISO country filter for sector news (India)
    news_timeout_seconds: int = 20

    # --- secrets ---
    openrouter_api_key: SecretStr | None = None
    marketaux_api_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    whatsapp_api_key: SecretStr | None = None
    newsapi_key: SecretStr | None = None

    # --- scheduler ---
    sunday_full_run_hour_ist: int = 19
    monday_revalidation_hour_ist: int = 9
    monday_revalidation_minute_ist: int = 10
    midweek_mini_screen_enabled: bool = False
    daily_exit_monitor_minutes: list[int] = Field(
        default_factory=lambda: [930, 1015, 1100, 1330, 1500]
    )
    # NSE's bhavcopy delivery report is typically published by ~19:00 IST
    daily_delivery_fetch_hour_ist: int = 19
    daily_delivery_fetch_minute_ist: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    @field_validator(
        "risk_per_trade_pct",
        "max_position_pct_of_adv",
        "sector_cap_pct_of_pool",
        "pairwise_correlation_max",
        "drawdown_governor_trigger_pct",
        "drawdown_governor_halving_factor",
        "stt_pct",
        "exchange_pct",
        "gst_pct",
        "stamp_duty_pct",
        "sentiment_pillar_weight",
    )
    @classmethod
    def _pct_in_unit_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("percentage field must be within [0, 1]")
        return v

    @field_validator("expectancy_floor_R")
    @classmethod
    def _expectancy_floor_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(
                "expectancy_floor_R must be positive (a non-positive floor disables A4)"
            )
        return v

    @model_validator(mode="after")
    def _prod_guards(self) -> Settings:
        if self.environment == "prod":
            if self.db_url.startswith("sqlite"):
                raise ValueError("sqlite db_url is not allowed in prod")
            if self.freshness_assert_enabled is False:
                raise ValueError("freshness_assert_enabled must be True in prod (B11)")
            if self.risk_per_trade_pct > 0.02:
                raise ValueError("risk_per_trade_pct must be <= 0.02 in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
