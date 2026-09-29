import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import hashlib
import traceback
import re
import io
import time
from datetime import datetime, timedelta

import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ============================================================
# IIFL VCP CHAMPION SCANNER
# Minervini-style Fundamental + Trend + VCP + Pivot scoring
#
# IMPORTANT:
# 1. Keep your existing market_data.py in the same repository.
# 2. Keep your existing vcp.py in the same repository if used
#    elsewhere. This file contains its own VCP engine, so the
#    scanner remains usable even if vcp.py is unavailable.
# 3. Fundamentals are imported from a Screener.in CSV export.
#    IIFL market-data APIs provide price/volume data, not the
#    full fundamental dataset required by this scoring model.
# ============================================================

st.set_page_config(
    page_title="IIFL VCP Champion Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# Styling
# -----------------------------
st.markdown("""
<style>
.stApp { background:#0e1117; }
.block-container { padding-top:1.2rem; }
.metric-card {
    background:#151a22;
    border:1px solid #293241;
    border-radius:12px;
    padding:14px;
    margin-bottom:8px;
}
.score-big { font-size:32px; font-weight:800; }
.small-muted { color:#9aa4b2; font-size:12px; }
.badge {
    display:inline-block;
    padding:5px 10px;
    border-radius:999px;
    font-weight:700;
    font-size:12px;
    border:1px solid #374151;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Constants
# -----------------------------
DEFAULT_HISTORY_DAYS = 400
MIN_HISTORY_ROWS = 120

SCREENER_QUERY = """Market Capitalization > 500
AND Sales growth 3Years > 15
AND Profit growth 3Years > 20
AND Sales latest quarter > Sales preceding year quarter
AND Net Profit latest quarter > Net Profit preceding year quarter
AND EPS latest quarter > EPS preceding year quarter
AND Return on equity > 15
AND Average return on equity 3Years > 15
AND Return on capital employed > 15
AND Average return on capital employed 5Years > 15
AND Debt to equity < 0.5
AND Cash from operations last year > 0
AND Pledged percentage < 5
AND Current price > DMA 50
AND DMA 50 > DMA 200
AND DMA 200 > DMA 200 previous day
AND Up from 52w low > 30
AND Down from 52w high < 20
AND Current price > 50"""

# ============================================================
# Helpers
# ============================================================

def clean_num(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    if isinstance(x, (int, float, np.number)):
        return float(x)
    s = str(x).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "—", "nan", "None", "NA", "N/A"):
        return np.nan
    mult = 1.0
    if s.endswith("Cr"):
        s = s[:-2]
    if s.endswith("L"):
        s = s[:-1]
        mult = 0.01
    try:
        return float(s) * mult
    except Exception:
        return np.nan


def normalize_symbol(symbol):
    if symbol is None:
        return ""
    s = str(symbol).strip().upper()
    s = re.sub(r"\.(NS|NSE)$", "", s)
    s = re.sub(r"[-_]?EQ$", "", s)
    s = s.replace(" ", "")
    return s


def first_existing(df, names):
    for n in names:
        if n in df.columns:
            return n
    return None


def pct_change(a, b):
    if b is None or pd.isna(b) or b == 0:
        return np.nan
    return (a / b - 1.0) * 100.0


# ============================================================
# Technical indicators
# ============================================================

def add_indicators(df):
    x = df.copy()
    x = x.sort_values("Date").reset_index(drop=True)

    for c in ["Open", "High", "Low", "Close", "Volume"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")

    x["DMA20"] = x["Close"].rolling(20).mean()
    x["DMA50"] = x["Close"].rolling(50).mean()
    x["DMA200"] = x["Close"].rolling(200).mean()
    x["High52"] = x["High"].rolling(252).max()
    x["Low52"] = x["Low"].rolling(252).min()

    x["ATR14"] = atr(x, 14)
    x["AvgVol20"] = x["Volume"].rolling(20).mean()
    x["AvgVol50"] = x["Volume"].rolling(50).mean()

    delta = x["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    x["RSI14"] = 100 - (100 / (1 + rs))

    x["Return20"] = x["Close"].pct_change(20) * 100
    x["Return60"] = x["Close"].pct_change(60) * 100

    return x


def atr(df, period=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev).abs(),
            (low - prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


# ============================================================
# VCP ENGINE
# ============================================================

def local_pivots(df, window=5):
    high = df["High"]
    lows = df["Low"]

    swing_high = high[(high == high.rolling(window * 2 + 1, center=True).max())]
    swing_low = lows[(lows == lows.rolling(window * 2 + 1, center=True).min())]

    return swing_high.dropna(), swing_low.dropna()


def find_base_and_pivot(df):
    """
    Detect a practical consolidation base from the recent history.
    The algorithm is deliberately conservative:
    - looks at the most recent 60-160 sessions
    - identifies the highest high
    - measures corrections from that high
    - chooses a pivot near the upper part of the recent base
    """
    x = df.dropna(subset=["High", "Low", "Close"]).copy()
    if len(x) < 80:
        return {
            "base_start": None,
            "base_end": None,
            "pivot": np.nan,
            "base_high": np.nan,
            "base_low": np.nan,
        }

    end = len(x) - 1
    lookback = min(160, len(x))
    start = max(0, len(x) - lookback)
    w = x.iloc[start:].copy()

    # Highest high in the recent base-search window.
    base_high = float(w["High"].max())
    high_idx = w["High"].idxmax()

    # Prefer a recent high if the absolute high is too old.
    recent60 = x.iloc[max(0, len(x)-60):]
    recent_high = float(recent60["High"].max())

    if pd.notna(recent_high):
        base_high = recent_high

    # Low of the recent consolidation.
    base_low = float(w["Low"].min())

    # Pivot: highest high of the final 20 sessions, excluding the
    # current day to reduce look-ahead when used as a pre-breakout setup.
    prior = x.iloc[max(0, len(x)-21):-1]
    if len(prior) >= 5:
        pivot = float(prior["High"].max())
    else:
        pivot = float(x["High"].iloc[-1])

    # Base dates.
    return {
        "base_start": w["Date"].iloc[0],
        "base_end": w["Date"].iloc[-1],
        "pivot": pivot,
        "base_high": base_high,
        "base_low": base_low,
    }


def contraction_depths(df, pivot, max_depths=5):
    """
    Find meaningful pullbacks inside the recent base.
    Each contraction is measured as:
    (swing high - following swing low) / swing high.
    """
    x = df.copy().reset_index(drop=True)
    if len(x) < 60 or not np.isfinite(pivot):
        return []

    # Work on recent 160 bars.
    x = x.iloc[-min(160, len(x)):].reset_index(drop=True)

    # Smooth high/low lightly to reduce one-day noise.
    x["HH"] = x["High"].rolling(3, center=True).max()
    x["LL"] = x["Low"].rolling(3, center=True).min()

    # Candidate local peaks.
    peaks = []
    for i in range(3, len(x)-3):
        if x.loc[i, "High"] >= x.loc[i-3:i+3, "High"].max():
            peaks.append(i)

    contractions = []
    for p in peaks:
        # Search for the lowest low after the peak before another
        # meaningful rally / end of the window.
        end = min(len(x)-1, p + 35)
        if end <= p + 4:
            continue

        segment = x.iloc[p+1:end+1]
        if segment.empty:
            continue

        low_idx = segment["Low"].idxmin()
        low_price = float(segment.loc[low_idx, "Low"])
        high_price = float(x.loc[p, "High"])

        if high_price <= 0:
            continue

        depth = (high_price - low_price) / high_price * 100.0

        # Ignore tiny noise corrections and huge bear-market-like drops.
        if 2.0 <= depth <= 40.0:
            contractions.append(
                {
                    "peak_index": p,
                    "low_index": int(low_idx),
                    "depth": depth,
                }
            )

    # Keep distinct contractions separated in time.
    contractions = sorted(contractions, key=lambda z: z["low_index"])
    filtered = []
    for c in contractions:
        if not filtered or c["low_index"] - filtered[-1]["low_index"] >= 5:
            filtered.append(c)
        elif c["depth"] > filtered[-1]["depth"]:
            filtered[-1] = c

    # Prefer the latest sequence of up to 5 contractions.
    return filtered[-max_depths:]


def calculate_vcp(df):
    x = add_indicators(df)

    if len(x) < MIN_HISTORY_ROWS:
        return {
            "valid": False,
            "reason": f"Need at least {MIN_HISTORY_ROWS} daily candles.",
        }

    base = find_base_and_pivot(x)
    pivot = base["pivot"]
    close = float(x["Close"].iloc[-1])

    contractions = contraction_depths(x, pivot)

    depths = [float(c["depth"]) for c in contractions[-5:]]

    # A VCP needs at least three meaningful contractions for this model.
    count = len(depths)

    decreasing_pairs = 0
    if count >= 2:
        for i in range(1, count):
            if depths[i] < depths[i-1]:
                decreasing_pairs += 1

    strict_decreasing = count >= 3 and decreasing_pairs >= count - 1

    final_contraction = depths[-1] if depths else np.nan
    first_contraction = depths[0] if depths else np.nan

    # Price tightness near current price.
    last5 = x.tail(5)
    last10 = x.tail(10)
    tight5 = pct_change(last5["High"].max(), last5["Low"].min())
    tight10 = pct_change(last10["High"].max(), last10["Low"].min())

    # pct_change(max high, min low) is not a range percentage,
    # so use explicit denominator.
    tight5 = (
        (last5["High"].max() - last5["Low"].min())
        / last5["Low"].min() * 100
        if last5["Low"].min() > 0 else np.nan
    )
    tight10 = (
        (last10["High"].max() - last10["Low"].min())
        / last10["Low"].min() * 100
        if last10["Low"].min() > 0 else np.nan
    )

    # Volume dry-up: compare recent 10-session average with
    # the preceding 40-session average.
    recent_vol = x["Volume"].tail(10).mean()
    prior_vol = x["Volume"].tail(50).head(40).mean()

    if prior_vol and prior_vol > 0:
        volume_dryup = max(0.0, (1 - recent_vol / prior_vol) * 100)
    else:
        volume_dryup = np.nan

    # Base position: where current price sits inside the recent base.
    base_low = base["base_low"]
    base_high = base["base_high"]
    if base_high > base_low:
        base_position = (close - base_low) / (base_high - base_low) * 100
    else:
        base_position = np.nan

    # Distance from pivot.
    distance_to_pivot = (pivot - close) / pivot * 100 if pivot > 0 else np.nan

    # VCP score = 30.
    vcp_score = 0.0

    # A. Contraction sequence — 8
    if count >= 4:
        vcp_score += 5
    elif count >= 3:
        vcp_score += 4

    if strict_decreasing:
        vcp_score += 3

    # B. Depth contraction — 6
    if count >= 3:
        if strict_decreasing and final_contraction <= 8:
            vcp_score += 6
        elif strict_decreasing and final_contraction <= 12:
            vcp_score += 5
        elif strict_decreasing:
            vcp_score += 4
        elif final_contraction < first_contraction:
            vcp_score += 3

    # C. Price tightness — 5
    if pd.notna(tight5) and tight5 <= 3:
        vcp_score += 3
    elif pd.notna(tight10) and tight10 <= 5:
        vcp_score += 2

    # Add tightness bonus only when reasonably controlled.
    if pd.notna(tight10) and tight10 <= 5:
        vcp_score += 2
    elif pd.notna(tight10) and tight10 <= 8:
        vcp_score += 1

    vcp_score = min(vcp_score, 25)  # reserve volume/base points below

    # D. Volume dry-up — 5
    volume_points = 0
    if pd.notna(volume_dryup):
        if volume_dryup >= 40:
            volume_points = 5
        elif volume_dryup >= 25:
            volume_points = 4
        elif volume_dryup >= 10:
            volume_points = 2
        elif volume_dryup >= 0:
            volume_points = 1

    # E. Base position — 3
    position_points = 0
    if pd.notna(base_position):
        if base_position >= 80:
            position_points = 3
        elif base_position >= 70:
            position_points = 2
        elif base_position >= 50:
            position_points = 1

    # F. Base duration — 3
    # Use available recent history as a practical approximation.
    duration_days = min(160, len(x))
    if duration_days >= 42:
        duration_points = 3
    elif duration_days >= 28:
        duration_points = 2
    elif duration_days >= 21:
        duration_points = 1
    else:
        duration_points = 0

    # The base score above may be <=25. Add remaining components.
    vcp_score += volume_points + position_points + duration_points
    vcp_score = min(30, float(vcp_score))

    # Setup status.
    if pd.isna(distance_to_pivot):
        setup = "NO PIVOT"
    elif close > pivot:
        setup = "BREAKOUT"
    elif distance_to_pivot <= 3:
        setup = "PRIME"
    elif distance_to_pivot <= 7:
        setup = "READY"
    elif distance_to_pivot <= 12:
        setup = "DEVELOPING"
    else:
        setup = "TOO EARLY"

    return {
        "valid": True,
        "pivot": pivot,
        "close": close,
        "distance_to_pivot": distance_to_pivot,
        "contractions": depths,
        "contraction_count": count,
        "strict_decreasing": strict_decreasing,
        "first_contraction": first_contraction,
        "final_contraction": final_contraction,
        "tight5": tight5,
        "tight10": tight10,
        "volume_dryup": volume_dryup,
        "base_position": base_position,
        "duration_days": duration_days,
        "vcp_score": vcp_score,
        "setup": setup,
        "base_start": base["base_start"],
        "base_end": base["base_end"],
        "base_high": base_high,
        "base_low": base_low,
    }


# ============================================================
# Trend score — 20
# ============================================================

def calculate_trend_score(df):
    x = add_indicators(df)
    r = x.iloc[-1]

    score = 0
    checks = {}

    checks["Price > 50 DMA"] = bool(r["Close"] > r["DMA50"]) if pd.notna(r["DMA50"]) else False
    checks["50 DMA > 200 DMA"] = bool(r["DMA50"] > r["DMA200"]) if pd.notna(r["DMA200"]) else False

    if len(x) >= 201 and pd.notna(x["DMA200"].iloc[-1]) and pd.notna(x["DMA200"].iloc[-21]):
        checks["200 DMA rising"] = bool(x["DMA200"].iloc[-1] > x["DMA200"].iloc[-21])
    else:
        checks["200 DMA rising"] = False

    checks["Price > 200 DMA"] = bool(r["Close"] > r["DMA200"]) if pd.notna(r["DMA200"]) else False

    checks["Within 20% of 52W high"] = (
        bool(r["Close"] >= r["High52"] * 0.80)
        if pd.notna(r["High52"]) else False
    )

    checks[">30% above 52W low"] = (
        bool(r["Close"] >= r["Low52"] * 1.30)
        if pd.notna(r["Low52"]) else False
    )

    # 20/50 structure
    checks["20 DMA > 50 DMA"] = (
        bool(r["DMA20"] > r["DMA50"])
        if pd.notna(r["DMA20"]) and pd.notna(r["DMA50"]) else False
    )

    checks["RS / momentum positive"] = (
        bool(r["Return60"] > 0)
        if pd.notna(r["Return60"]) else False
    )

    score += 3 if checks["Price > 50 DMA"] else 0
    score += 4 if checks["50 DMA > 200 DMA"] else 0
    score += 3 if checks["200 DMA rising"] else 0
    score += 2 if checks["Price > 200 DMA"] else 0
    score += 3 if checks["Within 20% of 52W high"] else 0
    score += 2 if checks[">30% above 52W low"] else 0
    score += 2 if checks["20 DMA > 50 DMA"] else 0
    score += 1 if checks["RS / momentum positive"] else 0

    hard_gate = (
        checks["Price > 50 DMA"]
        and checks["50 DMA > 200 DMA"]
        and checks["200 DMA rising"]
    )

    return {
        "trend_score": int(score),
        "hard_gate": hard_gate,
        "checks": checks,
        "dma20": r["DMA20"],
        "dma50": r["DMA50"],
        "dma200": r["DMA200"],
        "high52": r["High52"],
        "low52": r["Low52"],
        "rsi": r["RSI14"],
    }


# ============================================================
# Breakout score — 10
# ============================================================

def calculate_breakout_score(df, pivot):
    x = add_indicators(df)
    r = x.iloc[-1]

    if not np.isfinite(pivot) or pivot <= 0:
        return {"score": 0, "breakout": False, "volume_ratio": np.nan}

    volume_ratio = (
        r["Volume"] / r["AvgVol50"]
        if pd.notna(r["AvgVol50"]) and r["AvgVol50"] > 0
        else np.nan
    )

    breakout = bool(r["Close"] > pivot)
    score = 0

    if breakout:
        score += 3

    if pd.notna(volume_ratio):
        if volume_ratio >= 2.0:
            score += 4
        elif volume_ratio >= 1.5:
            score += 3

    day_range = r["High"] - r["Low"]
    if day_range > 0:
        close_strength = (r["Close"] - r["Low"]) / day_range * 100
    else:
        close_strength = 50

    if close_strength >= 80:
        score += 2

    # Tight breakout base bonus.
    if breakout and len(x) >= 10:
        rng10 = (
            (x["High"].tail(10).max() - x["Low"].tail(10).min())
            / x["Low"].tail(10).min() * 100
            if x["Low"].tail(10).min() > 0 else np.nan
        )
        if pd.notna(rng10) and rng10 <= 8:
            score += 1

    return {
        "score": min(10, int(score)),
        "breakout": breakout,
        "volume_ratio": volume_ratio,
        "close_strength": close_strength,
    }


# ============================================================
# Fundamental scoring — 40
# ============================================================

def prepare_fundamental_df(df):
    x = df.copy()
    x.columns = [
        re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")
        for c in x.columns
    ]

    # Common Screener column aliases.
    aliases = {
        "symbol": ["symbol", "nse_code", "nsecode", "security_name", "name", "company"],
        "market_cap": ["market_cap", "market_capitalization", "mar_cap_rs_cr"],
        "sales_growth_3y": ["sales_growth_3years", "sales_growth_3years_pct", "sales_growth_3y"],
        "profit_growth_3y": ["profit_growth_3years", "profit_growth_3years_pct", "profit_growth_3y"],
        "sales_qoq_yoy": ["yoy_quarterly_sales_growth", "sales_qtr_var", "quarterly_sales_growth"],
        "profit_qoq_yoy": ["yoy_quarterly_profit_growth", "qtr_profit_var", "quarterly_profit_growth"],
        "eps_qoq_yoy": ["eps_latest_quarter_growth", "yoy_quarterly_eps_growth", "eps_growth"],
        "roe": ["return_on_equity", "roe", "roe_percent"],
        "roe_3y": ["average_return_on_equity_3years", "roe_3yr_avg", "roe_3y"],
        "roce": ["return_on_capital_employed", "roce", "roce_percent"],
        "roce_5y": ["average_return_on_capital_employed_5years", "roce_5yr_avg", "roce_5y"],
        "de": ["debt_to_equity", "debt_equity", "d_e"],
        "pledge": ["pledged_percentage", "pledge", "promoter_pledge"],
        "cfo": ["cash_from_operations_last_year", "cash_from_operating_activity", "cfo"],
    }

    resolved = {}
    for key, opts in aliases.items():
        resolved[key] = first_existing(x, opts)

    return x, resolved


def get_row_value(row, resolved, key):
    col = resolved.get(key)
    if col is None or col not in row.index:
        return np.nan
    return clean_num(row[col])


def fundamental_score(row, resolved):
    # 40 points exactly.
    s = 0
    details = {}

    sales3 = get_row_value(row, resolved, "sales_growth_3y")
    profit3 = get_row_value(row, resolved, "profit_growth_3y")
    salesq = get_row_value(row, resolved, "sales_qoq_yoy")
    profitq = get_row_value(row, resolved, "profit_qoq_yoy")
    epsq = get_row_value(row, resolved, "eps_qoq_yoy")
    roe = get_row_value(row, resolved, "roe")
    roe3 = get_row_value(row, resolved, "roe_3y")
    roce = get_row_value(row, resolved, "roce")
    roce5 = get_row_value(row, resolved, "roce_5y")
    de = get_row_value(row, resolved, "de")
    pledge = get_row_value(row, resolved, "pledge")
    cfo = get_row_value(row, resolved, "cfo")

    details["3Y Sales >20%"] = 5 if pd.notna(sales3) and sales3 > 20 else 0
    details["3Y Profit >25%"] = 5 if pd.notna(profit3) and profit3 > 25 else 0
    details["Quarter Sales >20%"] = 5 if pd.notna(salesq) and salesq > 20 else 0
    details["Quarter EPS >20%"] = 5 if pd.notna(epsq) and epsq > 20 else 0
    details["Quarter Profit >20%"] = 5 if pd.notna(profitq) and profitq > 20 else 0

    details["ROE >20%"] = 3 if pd.notna(roe) and roe > 20 else 0
    if details["ROE >20%"] == 0 and pd.notna(roe3) and roe3 > 20:
        details["ROE >20%"] = 3

    details["ROCE >20%"] = 3 if pd.notna(roce) and roce > 20 else 0
    if details["ROCE >20%"] == 0 and pd.notna(roce5) and roce5 > 20:
        details["ROCE >20%"] = 3

    details["D/E <0.5"] = 3 if pd.notna(de) and de < 0.5 else 0
    details["Positive CFO"] = 3 if pd.notna(cfo) and cfo > 0 else 0
    details["Pledge <5%"] = 3 if pd.notna(pledge) and pledge < 5 else 0

    s = sum(details.values())

    return int(min(40, s)), details


# ============================================================
# Champion classification
# ============================================================

def classify(total, hard_gate, vcp, breakout):
    if not hard_gate:
        return "TREND FAIL"
    if total >= 90 and vcp >= 24:
        return "CHAMPION"
    if total >= 80 and vcp >= 20:
        return "A+ SETUP"
    if total >= 70 and vcp >= 16:
        return "WATCH"
    if total >= 60:
        return "DEVELOPING"
    return "IGNORE"


# ============================================================
# IIFL compatibility layer
# ============================================================

def try_import_market_data():
    try:
        import market_data
        return market_data
    except Exception:
        return None


def discover_history_function(md):
    """
    Supports several likely names from the user's existing
    market_data.py without forcing a rewrite of that module.
    """
    if md is None:
        return None

    names = [
        "get_historical_data",
        "fetch_historical_data",
        "get_history",
        "fetch_history",
        "historical_data",
        "get_daily_history",
        "fetch_daily_history",
    ]

    for name in names:
        fn = getattr(md, name, None)
        if callable(fn):
            return fn

    return None


def normalize_history_result(result):
    if result is None:
        return None

    if isinstance(result, pd.DataFrame):
        x = result.copy()
    elif isinstance(result, list):
        x = pd.DataFrame(result)
    elif isinstance(result, dict):
        # Common API shapes.
        if isinstance(result.get("result"), list):
            x = pd.DataFrame(result["result"])
        elif isinstance(result.get("data"), list):
            x = pd.DataFrame(result["data"])
        elif isinstance(result.get("result"), dict):
            payload = result["result"]
            if isinstance(payload.get("data"), list):
                x = pd.DataFrame(payload["data"])
            else:
                x = pd.DataFrame(payload)
        else:
            return None
    else:
        return None

    if x.empty:
        return None

    # Normalize common IIFL / broker field names.
    mapping = {}
    for c in x.columns:
        k = str(c).lower().replace("_", "").replace(" ", "")
        if k in ("date", "datetime", "timestamp", "time"):
            mapping[c] = "Date"
        elif k in ("open", "openprice"):
            mapping[c] = "Open"
        elif k in ("high", "highprice"):
            mapping[c] = "High"
        elif k in ("low", "lowprice"):
            mapping[c] = "Low"
        elif k in ("close", "closeprice", "ltp"):
            mapping[c] = "Close"
        elif k in ("volume", "vol", "qty", "totaltradedquantity"):
            mapping[c] = "Volume"

    x = x.rename(columns=mapping)

    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    if not all(c in x.columns for c in required):
        return None

    x["Date"] = pd.to_datetime(x["Date"], errors="coerce")
    for c in required[1:]:
        x[c] = pd.to_numeric(x[c], errors="coerce")

    x = x.dropna(subset=required).sort_values("Date").drop_duplicates("Date")
    return x.reset_index(drop=True)


def call_existing_history(md, symbol, instrument_id, days):
    fn = discover_history_function(md)
    if fn is None:
        return None, "No compatible historical-data function found in market_data.py."

    attempts = [
        {"symbol": symbol, "instrument_id": instrument_id, "days": days},
        {"symbol": symbol, "instrumentId": instrument_id, "days": days},
        {"instrument_id": instrument_id, "days": days},
        {"instrumentId": instrument_id, "days": days},
        {"symbol": symbol},
    ]

    errors = []

    for kwargs in attempts:
        try:
            result = fn(**kwargs)
            data = normalize_history_result(result)
            if data is not None and len(data) >= 20:
                return data, None
        except TypeError as e:
            errors.append(str(e))
            continue
        except Exception as e:
            errors.append(str(e))
            continue

    # Positional fallback.
    for args in [
        (symbol, instrument_id, days),
        (instrument_id, days),
        (symbol, days),
    ]:
        try:
            result = fn(*args)
            data = normalize_history_result(result)
            if data is not None and len(data) >= 20:
                return data, None
        except Exception as e:
            errors.append(str(e))

    return None, " | ".join(errors[-3:])


# ============================================================
# Manual CSV fallback
# ============================================================

def parse_price_csv(uploaded):
    if uploaded is None:
        return None

    try:
        x = pd.read_csv(uploaded)
    except Exception:
        uploaded.seek(0)
        x = pd.read_excel(uploaded)

    x.columns = [str(c).strip() for c in x.columns]
    cols = {c.lower(): c for c in x.columns}

    def find(names):
        for n in names:
            if n.lower() in cols:
                return cols[n.lower()]
        return None

    datec = find(["Date", "Datetime", "Timestamp"])
    openc = find(["Open"])
    highc = find(["High"])
    lowc = find(["Low"])
    closec = find(["Close", "LTP"])
    volc = find(["Volume", "Vol"])

    if not all([datec, openc, highc, lowc, closec, volc]):
        raise ValueError("Price CSV must contain Date, Open, High, Low, Close and Volume.")

    x = x.rename(
        columns={
            datec: "Date",
            openc: "Open",
            highc: "High",
            lowc: "Low",
            closec: "Close",
            volc: "Volume",
        }
    )
    x["Date"] = pd.to_datetime(x["Date"], errors="coerce")
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")

    return x.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"]).sort_values("Date")


# ============================================================
# Charts
# ============================================================

def make_chart(df, pivot=np.nan, title="VCP Chart"):
    x = add_indicators(df)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.58, 0.20, 0.22],
    )

    fig.add_trace(
        go.Candlestick(
            x=x["Date"],
            open=x["Open"],
            high=x["High"],
            low=x["Low"],
            close=x["Close"],
            name="Price",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=x["Date"],
            y=x["DMA20"],
            name="20 DMA",
            line=dict(width=1),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x["Date"],
            y=x["DMA50"],
            name="50 DMA",
            line=dict(width=1.5),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x["Date"],
            y=x["DMA200"],
            name="200 DMA",
            line=dict(width=1.5),
        ),
        row=1,
        col=1,
    )

    if np.isfinite(pivot):
        fig.add_hline(
            y=pivot,
            line_dash="dash",
            annotation_text=f"Pivot ₹{pivot:,.2f}",
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Bar(
            x=x["Date"],
            y=x["Volume"],
            name="Volume",
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=x["Date"],
            y=x["RSI14"],
            name="RSI",
        ),
        row=3,
        col=1,
    )
    fig.add_hline(y=70, line_dash="dot", row=3, col=1)
    fig.add_hline(y=40, line_dash="dot", row=3, col=1)

    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=760,
        xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h"),
    )

    return fig


# ============================================================
# Sidebar
# ============================================================

st.sidebar.title("⚙️ Scanner Controls")

history_days = st.sidebar.slider(
    "Historical candles",
    min_value=200,
    max_value=700,
    value=400,
    step=50,
)

min_score = st.sidebar.slider(
    "Minimum Champion Score",
    min_value=40,
    max_value=95,
    value=70,
    step=5,
)

require_trend = st.sidebar.checkbox(
    "Require Trend Template",
    value=True,
)

require_vcp = st.sidebar.checkbox(
    "Require 3+ VCP contractions",
    value=True,
)

show_chart = st.sidebar.checkbox(
    "Show chart for selected stock",
    value=True,
)

st.sidebar.divider()
st.sidebar.markdown("### Screener.in Fundamental Filter")
st.sidebar.code(SCREENER_QUERY, language="text")

st.sidebar.markdown(
    "Export the results of this query from Screener.in as CSV and upload it below."
)

fund_file = st.sidebar.file_uploader(
    "Upload Screener.in CSV",
    type=["csv", "xlsx"],
    key="fundamental_csv",
)

price_file = st.sidebar.file_uploader(
    "Optional price CSV for testing",
    type=["csv", "xlsx"],
    key="price_csv",
)

# ============================================================
# Header
# ============================================================

st.title("📈 IIFL VCP Champion Scanner")
st.caption(
    "Minervini-style Fundamental + Trend + VCP + Pivot + Breakout scoring"
)

st.info(
    "Workflow: Screener.in fundamentals → IIFL daily OHLCV → Trend Template → "
    "VCP contractions → volume dry-up → pivot → breakout → 100-point score."
)

# ============================================================
# Fundamental data
# ============================================================

fund_df = None
fund_resolved = {}

if fund_file is not None:
    try:
        if fund_file.name.lower().endswith(".csv"):
            fund_df = pd.read_csv(fund_file)
        else:
            fund_df = pd.read_excel(fund_file)

        fund_df, fund_resolved = prepare_fundamental_df(fund_df)

        symbol_col = fund_resolved.get("symbol")
        if symbol_col:
            fund_df["_symbol_norm"] = fund_df[symbol_col].apply(normalize_symbol)

        st.success(
            f"Loaded {len(fund_df):,} fundamental rows from {fund_file.name}."
        )
    except Exception as e:
        st.error(f"Could not read fundamental file: {e}")

# ============================================================
# Data source
# ============================================================

md = try_import_market_data()

if md is None:
    st.warning(
        "market_data.py was not found. Your scanner can still analyze an uploaded "
        "price CSV, but IIFL automatic scanning requires your existing market_data.py."
    )

# ============================================================
# Watchlist
# ============================================================

watchlist_text = st.text_area(
    "Watchlist / NSE symbols",
    value="",
    height=100,
    placeholder="RELIANCE, TCS, HDFCBANK, ICICIBANK, BHARTIARTL",
)

if watchlist_text.strip():
    symbols = [
        normalize_symbol(s)
        for s in re.split(r"[,\\s]+", watchlist_text.strip())
        if s.strip()
    ]
elif fund_df is not None and fund_resolved.get("symbol"):
    symbols = fund_df["_symbol_norm"].dropna().drop_duplicates().tolist()
else:
    symbols = []

# ============================================================
# Analyze single symbol
# ============================================================

def analyze_symbol(symbol):
    symbol = normalize_symbol(symbol)

    # Fundamental row.
    fscore = 0
    fdetails = {}
    frow = None

    if fund_df is not None and "_symbol_norm" in fund_df.columns:
        matches = fund_df[fund_df["_symbol_norm"] == symbol]
        if not matches.empty:
            frow = matches.iloc[0]
            fscore, fdetails = fundamental_score(frow, fund_resolved)

    # Price data.
    price_df = None
    data_error = None

    # Uploaded price CSV is a manual test source.
    if price_file is not None:
        try:
            price_df = parse_price_csv(price_file)
        except Exception as e:
            data_error = str(e)

    # Existing IIFL data layer.
    if price_df is None and md is not None:
        # Instrument ID is optional here because the user's existing
        # market_data.py may resolve it internally.
        price_df, err = call_existing_history(md, symbol, None, history_days)
        if price_df is None:
            data_error = err

    if price_df is None or len(price_df) < MIN_HISTORY_ROWS:
        return {
            "Symbol": symbol,
            "Total": fscore,
            "Fundamental": fscore,
            "Trend": 0,
            "VCP": 0,
            "Breakout": 0,
            "Status": "NO DATA",
            "Setup": "NO DATA",
            "Pivot": np.nan,
            "Distance": np.nan,
            "VCP Count": 0,
            "Final Contraction": np.nan,
            "Volume Dry-up": np.nan,
            "Volume Ratio": np.nan,
            "Error": data_error or "Insufficient price history.",
            "_df": None,
            "_fdetails": fdetails,
        }

    try:
        price_df = price_df.sort_values("Date").drop_duplicates("Date").reset_index(drop=True)
        trend = calculate_trend_score(price_df)
        vcp = calculate_vcp(price_df)
        pivot = vcp.get("pivot", np.nan) if vcp.get("valid") else np.nan
        brk = calculate_breakout_score(price_df, pivot)

        total = int(
            min(
                100,
                fscore
                + trend["trend_score"]
                + vcp.get("vcp_score", 0)
                + brk["score"],
            )
        )

        status = classify(
            total,
            trend["hard_gate"],
            vcp.get("vcp_score", 0),
            brk["score"],
        )

        if require_trend and not trend["hard_gate"]:
            status = "TREND FAIL"

        if require_vcp and vcp.get("contraction_count", 0) < 3:
            status = "NO VCP"

        return {
            "Symbol": symbol,
            "Total": total,
            "Fundamental": fscore,
            "Trend": trend["trend_score"],
            "VCP": vcp.get("vcp_score", 0),
            "Breakout": brk["score"],
            "Status": status,
            "Setup": vcp.get("setup", "UNKNOWN"),
            "Pivot": pivot,
            "Distance": vcp.get("distance_to_pivot", np.nan),
            "VCP Count": vcp.get("contraction_count", 0),
            "Final Contraction": vcp.get("final_contraction", np.nan),
            "Volume Dry-up": vcp.get("volume_dryup", np.nan),
            "Volume Ratio": brk.get("volume_ratio", np.nan),
            "Error": "",
            "_df": price_df,
            "_vcp": vcp,
            "_trend": trend,
            "_breakout": brk,
            "_fdetails": fdetails,
        }

    except Exception as e:
        return {
            "Symbol": symbol,
            "Total": fscore,
            "Fundamental": fscore,
            "Trend": 0,
            "VCP": 0,
            "Breakout": 0,
            "Status": "ERROR",
            "Setup": "ERROR",
            "Pivot": np.nan,
            "Distance": np.nan,
            "VCP Count": 0,
            "Final Contraction": np.nan,
            "Volume Dry-up": np.nan,
            "Volume Ratio": np.nan,
            "Error": str(e),
            "_df": price_df,
            "_fdetails": fdetails,
        }


# ============================================================
# Run scanner
# ============================================================

if not symbols:
    st.warning(
        "Enter symbols above or upload a Screener.in CSV. "
        "For automatic IIFL scanning, keep your existing market_data.py in the repository."
    )

run = st.button("🚀 RUN CHAMPION SCAN", type="primary", use_container_width=True)

if run:
    if not symbols:
        st.error("No symbols to scan.")
        st.stop()

    if len(symbols) > 250:
        st.warning("Scanning the first 250 symbols to avoid excessive API requests.")
        symbols = symbols[:250]

    results = []
    progress = st.progress(0)
    status_text = st.empty()

    for i, symbol in enumerate(symbols):
        status_text.write(f"Scanning {symbol} ({i+1}/{len(symbols)})...")
        result = analyze_symbol(symbol)
        results.append(result)
        progress.progress((i + 1) / len(symbols))

    progress.empty()
    status_text.empty()

    st.session_state["scan_results"] = results

# ============================================================
# Results
# ============================================================

results = st.session_state.get("scan_results", [])

if results:
    public_rows = []
    for r in results:
        public_rows.append(
            {
                "Symbol": r["Symbol"],
                "Score": r["Total"],
                "Fund": r["Fundamental"],
                "Trend": r["Trend"],
                "VCP": r["VCP"],
                "Breakout": r["Breakout"],
                "Status": r["Status"],
                "Setup": r["Setup"],
                "Pivot": r["Pivot"],
                "To Pivot %": r["Distance"],
                "VCP Cnt": r["VCP Count"],
                "Final C": r["Final Contraction"],
                "Vol Dry-up %": r["Volume Dry-up"],
                "Breakout Vol ×": r["Volume Ratio"],
            }
        )

    table = pd.DataFrame(public_rows)

    # Sort by total score, then VCP.
    table = table.sort_values(
        ["Score", "VCP"],
        ascending=[False, False],
    ).reset_index(drop=True)

    st.subheader("🏆 Champion Results")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks scanned", len(table))
    c2.metric("≥70 score", int((table["Score"] >= 70).sum()))
    c3.metric("≥80 score", int((table["Score"] >= 80).sum()))
    c4.metric("Breakouts", int((table["Setup"] == "BREAKOUT").sum()))

    st.dataframe(
        table.style.format(
            {
                "Score": "{:.0f}",
                "Fund": "{:.0f}",
                "Trend": "{:.0f}",
                "VCP": "{:.0f}",
                "Breakout": "{:.0f}",
                "Pivot": "₹{:,.2f}",
                "To Pivot %": "{:.2f}%",
                "Final C": "{:.2f}%",
                "Vol Dry-up %": "{:.1f}%",
                "Breakout Vol ×": "{:.2f}x",
            },
            na_rep="-",
        ),
        use_container_width=True,
        hide_index=True,
    )

    csv = table.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download Scan CSV",
        data=csv,
        file_name=f"vcp_champion_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

    st.divider()

    selectable = table["Symbol"].tolist()
    selected = st.selectbox("Inspect stock", selectable)

    selected_result = next(
        (r for r in results if r["Symbol"] == selected),
        None,
    )

    if selected_result:
        r = selected_result

        # Score header.
        h1, h2, h3, h4, h5 = st.columns(5)
        h1.metric("Champion Score", f'{r["Total"]}/100')
        h2.metric("Fundamental", f'{r["Fundamental"]}/40')
        h3.metric("Trend", f'{r["Trend"]}/20')
        h4.metric("VCP", f'{r["VCP"]}/30')
        h5.metric("Breakout", f'{r["Breakout"]}/10')

        st.markdown(
            f"### {r['Symbol']} — **{r['Status']}** | Setup: **{r['Setup']}**"
        )

        if r.get("_df") is not None and show_chart:
            st.plotly_chart(
                make_chart(
                    r["_df"],
                    r.get("Pivot", np.nan),
                    title=f"{r['Symbol']} — Minervini VCP Chart",
                ),
                use_container_width=True,
            )

        vcp = r.get("_vcp", {})
        trend = r.get("_trend", {})
        brk = r.get("_breakout", {})

        a, b, c = st.columns(3)

        with a:
            st.markdown("#### VCP Structure")
            st.write(f"Contractions: **{vcp.get('contraction_count', 0)}**")
            st.write(f"Sequence: **{vcp.get('contractions', [])}**")
            st.write(f"Strictly decreasing: **{vcp.get('strict_decreasing', False)}**")
            st.write(f"Final contraction: **{vcp.get('final_contraction', np.nan):.2f}%**")
            st.write(f"Volume dry-up: **{vcp.get('volume_dryup', np.nan):.1f}%**")
            st.write(f"Base position: **{vcp.get('base_position', np.nan):.1f}%**")

        with b:
            st.markdown("#### Pivot / Breakout")
            st.write(f"Pivot: **₹{r.get('Pivot', np.nan):,.2f}**")
            st.write(f"Distance: **{r.get('Distance', np.nan):.2f}%**")
            st.write(f"Breakout: **{brk.get('breakout', False)}**")
            st.write(f"Volume: **{brk.get('volume_ratio', np.nan):.2f}× 50D avg**")
            st.write(f"Close strength: **{brk.get('close_strength', np.nan):.1f}%**")

        with c:
            st.markdown("#### Trend Template")
            for name, passed in trend.get("checks", {}).items():
                st.write(("✅ " if passed else "❌ ") + name)

        st.markdown("#### Fundamental score breakdown")
        fdetails = r.get("_fdetails", {})
        if fdetails:
            fd = pd.DataFrame(
                [{"Condition": k, "Points": v} for k, v in fdetails.items()]
            )
            st.dataframe(fd, use_container_width=True, hide_index=True)
        else:
            st.info(
                "No matching Screener.in fundamental row was found. "
                "Upload the Screener CSV and make sure its symbol column contains NSE symbols."
            )

        if r.get("Error"):
            st.warning(r["Error"])

# ============================================================
# Methodology
# ============================================================

with st.expander("📚 Scoring methodology", expanded=False):
    st.markdown("""
### 100-point model

**Fundamental Leadership — 40**
- 3Y Sales >20% = 5
- 3Y Profit >25% = 5
- Quarterly Sales >20% = 5
- Quarterly EPS >20% = 5
- Quarterly Profit >20% = 5
- ROE >20% = 3
- ROCE >20% = 3
- D/E <0.5 = 3
- Positive CFO = 3
- Pledge <5% = 3

**Trend Template — 20**
- Price >50 DMA = 3
- 50 DMA >200 DMA = 4
- Rising 200 DMA = 3
- Price >200 DMA = 2
- Within 20% of 52W high = 3
- >30% above 52W low = 2
- 20 DMA >50 DMA = 2
- Positive 60-session momentum = 1

**VCP — 30**
- 3+ contractions
- C1 > C2 > C3
- Final contraction ideally <=8–10%
- Tight price action
- Volume dry-up
- Upper-base positioning
- Developed base

**Breakout — 10**
- Close > pivot
- Breakout volume >=1.5× 50D average
- >=2× receives the strongest volume component
- Strong close
- Tight-base breakout bonus
""")

st.caption(
    "This scanner is a research/decision-support tool. A high score is not a guarantee of future performance."
)
