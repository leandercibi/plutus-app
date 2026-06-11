from __future__ import annotations

import json
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd

RUNS_DIR = Path("/tmp/plutus_runs")


def new_run_id() -> str:
    return f"{date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"


def run_dir(run_id: str) -> Path:
    d = RUNS_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def ohlcv_cache_path(symbol: str) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR / f"ohlcv_{date.today().isoformat()}_{symbol}.parquet"


def save_ohlcv(symbol: str, df: pd.DataFrame) -> None:
    df.to_parquet(ohlcv_cache_path(symbol))


def load_ohlcv(symbol: str) -> pd.DataFrame | None:
    p = ohlcv_cache_path(symbol)
    return pd.read_parquet(p) if p.exists() else None


def save_stage(run_id: str, stage: str, data: object) -> None:
    (run_dir(run_id) / f"{stage}.json").write_text(json.dumps(data))


def load_stage(run_id: str, stage: str) -> object | None:
    p = run_dir(run_id) / f"{stage}.json"
    return json.loads(p.read_text()) if p.exists() else None


def cleanup_old_runs() -> None:
    """Delete run folders and ohlcv parquet files older than 24h."""
    if not RUNS_DIR.exists():
        return
    cutoff = datetime.now().timestamp() - 86400
    for p in RUNS_DIR.iterdir():
        if p.stat().st_mtime < cutoff:
            shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
