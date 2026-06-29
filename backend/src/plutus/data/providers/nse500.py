"""NSE-500 seed symbols for universe building.

These are the NSE 500 constituents as of 2026. The list is intentionally
hard-coded here rather than fetched live so the universe is deterministic.
Add or remove symbols via scripts/refresh_seed_universe.py.

Last updated: 2026-06-29
Symbol renames applied:
  ZOMATO      → ETERNAL     (renamed Oct 2024)
  AMARAJABAT  → ARE&M       (Amara Raja Energy & Mobility, renamed Oct 2023)
  MCDOWELL-N  → UNITDSPR    (United Spirits, symbol updated)
  NAVNETEDU   → NAVNETEDUL  (Navneet Education, symbol updated)
  REPCO       → REPCOHOME   (Repco Home Finance, symbol updated)
  PEL         → PIRAMALFIN  (Piramal Enterprises delisted Sep 2025; Piramal Finance listed Nov 2025)
  SAILIND     → SAIL        (Steel Authority of India, correct symbol)
  VBLLTD      → VBL         (Varun Beverages, correct symbol)
  GMRINFRA    → GMRAIRPORT  (GMR Airports Infrastructure, post-demerger symbol)
  LAURUS      → LAURUSLABS  (Laurus Labs, correct symbol)
  KFin        → KFINTECH    (Kfin Technologies, correct symbol)
  LEMON       → LEMONTREE   (Lemon Tree Hotels, correct symbol)
  AAPL        removed       (Apple Inc — not an NSE stock)
  TVSMOTORS   removed       (duplicate; TVSMOTOR already present)
  INTERGLOBE  removed       (duplicate; INDIGO already present)
  WHIRLPOOLINDIA removed    (duplicate; WHIRLPOOL already present)
  INDIGO (duplicate) removed (appeared twice)
"""
from __future__ import annotations

NSE500_SYMBOLS: list[str] = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
    "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT", "AXISBANK",
    "ASIANPAINT", "MARUTI", "TITAN", "ULTRACEMCO", "NESTLEIND",
    "WIPRO", "HCLTECH", "BAJFINANCE", "BAJAJFINSV", "SUNPHARMA",
    "TECHM", "INDUSINDBK", "TATAMOTORS", "NTPC", "ONGC", "POWERGRID",
    "COALINDIA", "TATASTEEL", "HINDALCO", "GRASIM", "CIPLA",
    "DRREDDY", "DIVISLAB", "APOLLOHOSP", "BRITANNIA", "PIDILITIND",
    "SIEMENS", "HAVELLS", "MUTHOOTFIN", "UNITDSPR", "VOLTAS",
    "TORNTPHARM", "LUPIN", "BIOCON", "AUROPHARMA", "ABBOTINDIA",
    "PIRAMALFIN", "BERGEPAINT", "WHIRLPOOL", "POLYCAB", "ASTRAL",
    "TRENT", "PAGEIND", "JUBLFOOD", "NAUKRI", "IRCTC",
    "LTIM", "LTTS", "COFORGE", "MPHASIS", "PERSISTENT", "OFSS",
    "HDFCLIFE", "SBILIFE", "ICICIPRULI", "MAXFINSERV",
    "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", "TVSMOTOR",
    "M&M", "ASHOKLEY", "BALKRISIND",
    "ADANIPORTS", "ADANIENT", "ADANIGREEN", "ADANIPOWER",
    "JSWSTEEL", "SAIL", "NMDC", "VEDL",
    "HDFCAMC", "ICICIGI", "SBICARD",
    "RECLTD", "PFC", "IRFC", "HUDCO",
    "INDIGO", "SPICEJET",
    "OBEROIRLTY", "DLF", "GODREJPROP", "PRESTIGE",
    "ALKEM", "IPCALAB", "NATCOPHARM", "GRANULES",
    "DEEPAKNTR", "PIIND", "ATUL", "NAVINFLUOR",
    "CROMPTON", "BLUESTARCO", "BATAINDIA", "VBL",
    "ETERNAL", "PAYTM", "NYKAA", "POLICYBZR",
    "DMART", "TATACONSUM", "GODREJCP",
    "GLENMARK", "TORNTPOWER", "CESC", "TATAPOWER",
    "BANKINDIA", "PNB", "CANBK", "UNIONBANK", "IOB",
    "FEDERALBNK", "IDFCFIRSTB", "BANDHANBNK", "RBLBANK",
    "MFSL", "CHOLAFIN", "M&MFIN", "SHRIRAMFIN",
    "MOTHERSON", "BOSCHLTD", "EXIDEIND", "ARE&M",
    "CONCOR", "GMRAIRPORT", "IRB", "KPRMILL",
    "APLAPOLLO", "HINDCOPPER", "RATNAMANI",
    "CERA", "KAJARIACER",
    "RELAXO", "CAMPUS", "METROBRAND",
    "ABCAPITAL", "CANFINHOME", "REPCOHOME", "AAVAS",
    "MARICO", "DABUR", "COLPAL", "EMAMILTD",
    "KANSAINER", "WABAG",
    "SYNGENE", "LAURUSLABS", "SUVEN", "NEULANDLAB",
    "DIXON", "AMBER", "KAYNES", "SYRMA",
    "CAMS", "KFINTECH", "CDSL",
    "NAVNETEDUL", "PCJEWELLER", "KSCL",
    "ELGIEQUIP", "GREAVESCOT", "THERMAX",
    "EIHOTEL", "CHALET", "LEMONTREE",
]
