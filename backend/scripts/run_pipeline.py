#!/usr/bin/env python3
"""Run the full Plutus pipeline locally and immediately.

Usage:
    python scripts/run_pipeline.py [--symbols RELIANCE,TCS,INFY]

If --symbols is not given, reads scripts/nse500.csv (NSE-500 universe).
Writes swing signals to the DB; prints a summary.
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("pipeline")


def _load_universe(symbols_arg: str | None) -> list[str]:
    if symbols_arg:
        return [s.strip() for s in symbols_arg.split(",")]
    csv_path = Path(__file__).parent / "nse500.csv"
    if not csv_path.exists():
        logger.error("nse500.csv not found — pass --symbols or create scripts/nse500.csv")
        sys.exit(1)
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "symbol" in reader.fieldnames:
            return [r["symbol"].strip() for r in reader if r["symbol"].strip()]
        f.seek(0)
        return [line.strip() for line in f if line.strip() and not line.startswith("symbol")]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Plutus pipeline")
    parser.add_argument("--symbols", help="Comma-separated NSE symbols (e.g. RELIANCE,TCS)")
    parser.add_argument("--dry-run", action="store_true", help="Print signals, don't save to DB")
    parser.add_argument("--run-id", help="Caller-supplied run id (else auto-generated)")
    args = parser.parse_args()

    from plutus.db.init_db import init_db
    from plutus.db.session import session_scope
    from plutus.config.settings import get_settings

    init_db()
    settings = get_settings()

    universe = _load_universe(args.symbols)
    logger.info("Universe: %d symbols", len(universe))

    # Import providers (built by workers)
    try:
        from plutus.data.providers.yfinance_provider import YFinanceProvider
        from plutus.data.providers.delivery_stub import DeliveryStubProvider
        from plutus.data.providers.vix_provider import VixYFinanceProvider
        from plutus.data.providers.breadth_provider import BreadthYFinanceProvider
        from plutus.data.providers.fii_dii_provider import FIIDIIStubProvider
        from plutus.data.providers.regime_builder import build_regime_inputs
    except ImportError as e:
        logger.error("Provider not yet available: %s", e)
        logger.error("Run the workers first or wait for them to complete.")
        sys.exit(1)

    from plutus.data.ohlcv import OHLCVChain
    from plutus.shared.regime.detector import RegimeDetector
    from plutus.shared.regime.snapshot import save_snapshot
    from plutus.alerts.factory import build_alert_monitor
    from plutus.alerts.formatter import AlertFormatter
    from plutus.scheduler.jobs import sunday_full_run_job

    ohlcv_chain = OHLCVChain(YFinanceProvider(), fallback=None)
    delivery_provider = DeliveryStubProvider()
    monitor = build_alert_monitor(settings)
    formatter = AlertFormatter()

    logger.info("Fetching regime inputs...")
    regime_inputs = build_regime_inputs(
        date.today(),
        VixYFinanceProvider(),
        BreadthYFinanceProvider(),
        FIIDIIStubProvider(),
    )
    logger.info("Regime inputs ready")

    if args.dry_run:
        from plutus.shared.regime.detector import RegimeDetector
        verdict = RegimeDetector(settings).classify(regime_inputs)
        logger.info("Dry run — regime=%s, skipping DB writes", verdict.label)
        return

    from plutus.scheduler.run_log import RunLog
    import uuid as _uuid

    run_id = args.run_id or f"sun-{_uuid.uuid4().hex[:8]}"
    started = datetime.utcnow()
    logger.info("Run id: %s", run_id)

    with session_scope() as session:
        RunLog(session).start("sunday_full_run", started, run_id)

    aborted_reason: str | None = None
    status = "OK"
    try:
        with session_scope() as session:
            result = sunday_full_run_job(
                universe=universe,
                ohlcv_chain=ohlcv_chain,
                delivery_provider=delivery_provider,
                regime_inputs=regime_inputs,
                session=session,
                settings=settings,
                monitor=monitor,
                formatter=formatter,
                now=started,
                run_id=run_id,
            )
        aborted_reason = result.aborted_reason
        status = "ABORTED" if aborted_reason else "OK"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline crashed")
        status = "FAILED"
        aborted_reason = str(exc)

    # Count THIS run's signals (not the latest run_id in DB).
    from plutus.db.session import session_scope as _ss
    from plutus.db.models import SwingSignal as _SS
    n = 0
    labels: set[str] = set()
    with _ss() as _s:
        run_sigs = _s.query(_SS).filter(_SS.run_id == run_id).all()
        n = len(run_sigs)
        labels = {sg.label for sg in run_sigs}
        # Persist run summary.
        RunLog(_s).end(
            run_id,
            status,  # type: ignore[arg-type]
            {"signals": n, "labels": sorted(labels), "aborted": aborted_reason},
            datetime.utcnow(),
        )

    logger.info("Pipeline complete: status=%s run_id=%s", status, run_id)
    logger.info("Signals written for %s: %d (labels: %s)", run_id, n, sorted(labels))
    if aborted_reason:
        logger.error("Aborted: %s", aborted_reason)


if __name__ == "__main__":
    main()
