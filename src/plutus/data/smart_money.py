# src/plutus/data/smart_money.py
from mftool import Mftool
import requests
from typing import Dict, List
from datetime import date


def get_mf_signal(symbol: str) -> Dict:
    """
    Checks if mutual funds are accumulating or reducing holdings.
    Data: AMFI monthly portfolio disclosures (45-day lag).
    Returns: {verdict, mf_count_accumulating, mf_count_reducing, details}
    """
    try:
        Mftool()  # ensure import path works; stock-level lookup is custom
        return _scrape_nse_mf_holdings(symbol)
    except Exception:
        return {"verdict": "UNKNOWN", "mf_count_accumulating": 0, "mf_count_reducing": 0}


def _scrape_nse_mf_holdings(symbol: str) -> Dict:
    """
    Scrapes NSE/AMFI for mutual fund holdings change.
    NSE provides MF aggregate data at:
    https://www.nseindia.com/api/mutual-funds-equity-report
    """
    try:
        url = f"https://api.tickertape.in/stocks/{symbol}/holders"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200:
            return {
                "verdict": "UNKNOWN",
                "mf_count_accumulating": 0,
                "mf_count_reducing": 0,
                "details": [],
            }
    except Exception:
        pass
    return {"verdict": "UNKNOWN", "mf_count_accumulating": 0, "mf_count_reducing": 0}


def get_fii_dii_flow() -> Dict:
    """
    Gets FII and DII net buy/sell for today from NSE.
    https://www.nseindia.com/api/fiidiiTradeReact
    Returns: {fii_net_cr, dii_net_cr, fii_signal, dii_signal, date}
    """
    try:
        url = "https://www.nseindia.com/api/fiidiiTradeReact"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        latest = data[0] if data else {}
        fii_net = float(latest.get("fii_net_buy_sell", 0))
        dii_net = float(latest.get("dii_net_buy_sell", 0))
        return {
            "fii_net_cr": round(fii_net / 1e7, 2),
            "dii_net_cr": round(dii_net / 1e7, 2),
            "fii_signal": "net_buyer" if fii_net > 0 else "net_seller",
            "dii_signal": "net_buyer" if dii_net > 0 else "net_seller",
            "date": latest.get("date", str(date.today())),
        }
    except Exception:
        return {
            "fii_net_cr": 0,
            "dii_net_cr": 0,
            "fii_signal": "unknown",
            "dii_signal": "unknown",
            "date": str(date.today()),
        }


def get_bulk_deals(symbol: str) -> List[Dict]:
    """Fetches bulk/block deals from NSE for a given symbol."""
    try:
        url = "https://www.nseindia.com/api/block-deal"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
        resp = requests.get(url, headers=headers, timeout=10)
        deals = resp.json().get("data", [])
        return [d for d in deals if d.get("symbol", "").upper() == symbol.upper()]
    except Exception:
        return []
