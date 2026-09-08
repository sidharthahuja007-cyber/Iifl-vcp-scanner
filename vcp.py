"""
vcp.py
Minervini VCP Engine
Version 1
"""

import numpy as np
import pandas as pd


# =====================================================
# Moving Averages
# =====================================================

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def sma(series, period):
    return series.rolling(period).mean()


# =====================================================
# Trend Template
# =====================================================

def trend_template(df):

    if len(df) < 220:
        return False

    close = df["Close"]

    ma50 = sma(close, 50)
    ma150 = sma(close, 150)
    ma200 = sma(close, 200)

    current = close.iloc[-1]

    score = 0

    if current > ma50.iloc[-1]:
        score += 1

    if current > ma150.iloc[-1]:
        score += 1

    if current > ma200.iloc[-1]:
        score += 1

    if ma50.iloc[-1] > ma150.iloc[-1]:
        score += 1

    if ma150.iloc[-1] > ma200.iloc[-1]:
        score += 1

    if ma200.iloc[-1] > ma200.iloc[-20]:
        score += 1

    high52 = close.tail(252).max()
    low52 = close.tail(252).min()

    if current >= low52 * 1.30:
        score += 1

    if current >= high52 * 0.75:
        score += 1

    return score >= 7, score


# =====================================================
# Volatility Contraction
# =====================================================

def contraction_list(df):

    highs = df["High"].tail(120).values
    lows = df["Low"].tail(120).values

    contractions = []

    for i in range(20, 120, 20):

        high = np.max(highs[-i:])
        low = np.min(lows[-i:])

        contraction = ((high - low) / high) * 100

        contractions.append(round(contraction, 2))

    return contractions


# =====================================================
# Check if contractions shrink
# =====================================================

def contraction_quality(contractions):

    if len(contractions) < 3:
        return False

    score = 0

    for i in range(len(contractions)-1):

        if contractions[i] > contractions[i+1]:
            score += 1

    return score >= 3


# =====================================================
# Volume Dry-up
# =====================================================

def volume_dryup(df):

    recent = df["Volume"].tail(10).mean()
    previous = df["Volume"].tail(50).mean()

    ratio = recent / previous

    return ratio < 0.70, round(ratio,2)


# =====================================================
# Pivot
# =====================================================

def pivot(df):

    return round(df["High"].tail(25).max(),2)


# =====================================================
# Tight Closing
# =====================================================

def tight_close(df):

    last10 = df.tail(10)

    highest = last10["High"].max()

    lowest = last10["Low"].min()

    range_pct = ((highest-lowest)/highest)*100

    return range_pct < 8, round(range_pct,2)


# =====================================================
# Main Analysis
# =====================================================

def analyze(df):

    trend_ok, trend_score = trend_template(df)

    contractions = contraction_list(df)

    contraction_ok = contraction_quality(contractions)

    volume_ok, volume_ratio = volume_dryup(df)

    tight_ok, tight_range = tight_close(df)

    buy_point = pivot(df)

    close = df["Close"].iloc[-1]

    distance = ((buy_point-close)/buy_point)*100

    score = 0

    if trend_ok:
        score += 30

    if contraction_ok:
        score += 25

    if volume_ok:
        score += 20

    if tight_ok:
        score += 15

    if abs(distance) < 5:
        score += 10

    if score >= 80:
        signal = "STRONG VCP"

    elif score >= 60:
        signal = "WATCHLIST"

    elif score >= 40:
        signal = "DEVELOPING"

    else:
        signal = "NO SETUP"

    return {

        "Score": score,

        "Signal": signal,

        "Trend Score": trend_score,

        "Contractions": contractions,

        "Volume Ratio": volume_ratio,

        "Pivot": buy_point,

        "Distance %": round(distance,2),

        "Tight Range %": tight_range

    }
