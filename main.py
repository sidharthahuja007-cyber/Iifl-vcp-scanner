import streamlit as st
import pandas as pd
import numpy as np
import requests
import hashlib
import json
import traceback
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from io import StringIO

# ============================================================
# PAGE CONFIG + THEME
# ============================================================

st.set_page_config(
    page_title="IIFL VCP Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #262d38;
                border-radius: 10px; padding: 12px 16px; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; }
    .block-container { padding-top: 1.5rem; }
    .stButton>button { border-radius: 6px; }
    .signal-badge {
        display: inline-block; padding: 3px 10px; border-radius: 12px;
        font-size: 0.75rem; font-weight: 600; margin-right: 4px;
    }
    .badge-strong { background:#0d3b28; color:#3fd68c; }
    .badge-watch  { background:#3a2e05; color:#e0b23c; }
    .badge-dev    { background:#1c2b4a; color:#5b8def; }
    .badge-none   { background:#2a2a2a; color:#888; }
    .badge-breakout { background:#4a1520; color:#ff5c7a; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# IIFL CONFIGURATION
# ============================================================

IIFL_BASE_URL = "https://api.iiflcapital.com/v1"
IIFL_LOGIN_URL = "https://markets.iiflcapital.com/?v=1&appkey=iDCmottF6T8VZr1"
IIFL_NSE_JSON_URL = f"{IIFL_BASE_URL}/contractfiles/NSEEQ.json"
IIFL_NSE_CSV_URL = f"{IIFL_BASE_URL}/contractfiles/NSEEQ.csv"
EXCHANGE_FALLBACKS = ["NSEEQ", "NSE", "N"]

FO_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "ITC.NS",
    "SBIN.NS", "BHARTIARTL.NS", "LT.NS", "AXISBANK.NS", "KOTAKBANK.NS",
    "HINDUNILVR.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "BAJFINANCE.NS",
    "BAJAJFINSV.NS", "ADANIENT.NS", "ADANIPORTS.NS", "NTPC.NS", "POWERGRID.NS",
    "BEL.NS", "HAL.NS", "BHEL.NS", "TRENT.NS", "DIXON.NS", "CDSL.NS", "MCX.NS",
    "POLYCAB.NS", "PERSISTENT.NS", "COFORGE.NS", "JUBLFOOD.NS", "PIDILITIND.NS",
    "DEEPAKNTR.NS", "SRF.NS", "TATAELXSI.NS", "MUTHOOTFIN.NS", "SHRIRAMFIN.NS",
    "AUROPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "LUPIN.NS",
    "ZYDUSLIFE.NS", "ABB.NS", "ABBOTINDIA.NS", "ABCAPITAL.NS", "ABFRL.NS",
    "ACC.NS", "ALKEM.NS", "AMBUJACEM.NS", "APLAPOLLO.NS", "APOLLOHOSP.NS",
    "APOLLOTYRE.NS", "ASHOKLEY.NS", "ASIANPAINT.NS", "ASTRAL.NS", "ATUL.NS",
    "AUBANK.NS", "BAJAJ-AUTO.NS", "BALKRISIND.NS", "BALRAMCHIN.NS",
    "BANDHANBNK.NS", "BANKBARODA.NS", "BATAINDIA.NS", "BERGEPAINT.NS",
    "BHARATFORG.NS", "BIOCON.NS", "BOSCHLTD.NS", "BPCL.NS", "BRITANNIA.NS",
    "CAMS.NS", "CANBK.NS", "CHOLAFIN.NS", "COALINDIA.NS", "COLPAL.NS",
    "CONCOR.NS", "COROMANDEL.NS", "CROMPTON.NS", "CUMMINSIND.NS", "DABUR.NS",
    "DALBHARAT.NS", "DELHIVERY.NS", "DLF.NS", "EICHERMOT.NS", "ESCORTS.NS",
    "EXIDEIND.NS", "FEDERALBNK.NS", "GAIL.NS", "GLENMARK.NS", "GMRINFRA.NS",
    "GODREJCP.NS", "GODREJPROP.NS", "GRASIM.NS", "HAVELLS.NS", "HCLTECH.NS",
    "HDFCAMC.NS", "HDFCLIFE.NS", "HEROMOTOCO.NS", "HINDALCO.NS", "HINDPETRO.NS",
    "ICICIGI.NS", "ICICIPRULI.NS", "IDFCFIRSTB.NS", "IEX.NS", "IGL.NS",
    "INDHOTEL.NS", "INDIAMART.NS", "INDIGO.NS", "INDUSINDBK.NS", "INDUSTOWER.NS",
    "IOC.NS", "IRCTC.NS", "IRFC.NS", "JINDALSTEL.NS", "JSWENERGY.NS",
    "JSWSTEEL.NS", "KALYANKJIL.NS", "L&TFH.NS", "LICHSGFIN.NS", "LICI.NS",
    "LODHA.NS", "LTIM.NS", "M&M.NS", "M&MFIN.NS", "MARICO.NS", "MFSL.NS",
    "MOTHERSON.NS", "MPHASIS.NS", "NATIONALUM.NS", "NAUKRI.NS", "NESTLEIND.NS",
    "NMDC.NS", "OBEROIRLTY.NS", "OFSS.NS", "ONGC.NS", "PAGEIND.NS", "PATANJALI.NS",
    "PEL.NS", "PETRONET.NS", "PFC.NS", "PHOENIXLTD.NS", "PIIND.NS", "PNB.NS",
    "RECLTD.NS", "SAIL.NS", "SBICARD.NS", "SBILIFE.NS", "SHREECEM.NS",
    "SIEMENS.NS", "SUNTV.NS", "TATACHEM.NS", "TATACOMM.NS", "TATACONSUM.NS",
    "TATAMOTORS.NS", "TATAPOWER.NS", "TATASTEEL.NS", "TECHM.NS", "TIINDIA.NS",
    "TORNTPHARM.NS", "TORNTPOWER.NS", "TVSMOTOR.NS", "UBL.NS", "UPL.NS",
    "VBL.NS", "VEDL.NS", "VOLTAS.NS", "WIPRO.NS", "ZOMATO.NS"
]
FO_STOCKS = list(dict.fromkeys(FO_STOCKS))


def mask(token, keep=4):
    if not token:
        return "None"
    token = str(token)
    if len(token) <= keep * 2:
        return "*" * len(token)
    return token[:keep] + "..." + token[-keep:]


# ============================================================
# AUTH
# ============================================================

def get_iifl_user_session(authcode, clientid):
    try:
        app_secret = st.secrets["IIFL_APP_SECRET"]
    except Exception:
        st.error("IIFL_APP_SECRET is missing from Streamlit Secrets.")
        return None
    try:
        checksum_string = str(clientid) + str(authcode) + str(app_secret)
        checksum = hashlib.sha256(checksum_string.encode("utf-8")).hexdigest()
        response = requests.post(
            f"{IIFL_BASE_URL}/getusersession", json={"checkSum": checksum}, timeout=30
        )
        if response.status_code != 200:
            st.error(f"IIFL login HTTP error: {response.status_code}")
            return None
        data = response.json()
        if data.get("status") == "Ok":
            session = data.get("userSession")
            if session:
                return session
        st.error("IIFL did not return a user session.")
        return None
    except Exception as e:
        st.error(f"IIFL authentication error: {e}")
        return None


query_params = st.query_params
authcode = query_params.get("authcode") or query_params.get("authCode")
clientid = query_params.get("clientid") or query_params.get("clientId")

if authcode and clientid and "iifl_user_session" not in st.session_state:
    with st.spinner("🔐 Connecting to IIFL..."):
        user_session = get_iifl_user_session(authcode, clientid)
    if user_session:
        st.session_state["iifl_user_session"] = user_session
        st.session_state["iifl_client_id"] = clientid
        st.query_params.clear()
        st.rerun()


def get_iifl_headers():
    session = st.session_state.get("iifl_user_session")
    if not session:
        return None
    return {
        "Authorization": f"Bearer {session}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


# ============================================================
# INSTRUMENT MASTER + LOOKUP
# ============================================================

@st.cache_data(ttl=86400)
def load_iifl_nse_instruments():
    try:
        r = requests.get(IIFL_NSE_JSON_URL, timeout=30)
        if r.status_code == 200:
            raw = r.json()
            records = None
            if isinstance(raw, list):
                records = raw
            elif isinstance(raw, dict):
                for key in ["result", "data", "instruments", "records"]:
                    if key in raw and isinstance(raw[key], list):
                        records = raw[key]
                        break
            if records:
                df = pd.DataFrame(records)
                if not df.empty:
                    return df
    except Exception:
        pass
    try:
        r = requests.get(IIFL_NSE_CSV_URL, timeout=30)
        if r.status_code == 200:
            df = pd.read_csv(StringIO(r.text))
            if not df.empty:
                return df
    except Exception:
        pass
    return None


def normalize_symbol(symbol):
    symbol = str(symbol).upper().strip()
    return (symbol.replace(".NS", "").replace(".NSE", "")
            .replace("-EQ", "").replace("_EQ", "").replace(" EQ", "").strip())


def find_instrument_id(record):
    if not isinstance(record, dict):
        return None
    for key in ["instrumentId", "InstrumentId", "instrumentID", "instrument_id",
                "NSEInstrumentId", "securityId", "scripCode", "token"]:
        if key in record:
            value = record[key]
            if value is not None and str(value).strip() not in ["", "nan", "None"]:
                return str(value)
    for key, value in record.items():
        if "instrumentid" in str(key).lower().replace("_", "") and value is not None:
            return str(value)
    return None


def find_iifl_instrument(symbol):
    instruments = load_iifl_nse_instruments()
    if instruments is None:
        return None
    target = normalize_symbol(symbol)
    for column in instruments.columns:
        try:
            values = instruments[column].astype(str).str.upper().str.strip()
            normalized = (values.str.replace(".NS", "", regex=False)
                          .str.replace("-EQ", "", regex=False)
                          .str.replace("_EQ", "", regex=False)
                          .str.replace(" EQ", "", regex=False).str.strip())
            match = instruments[normalized == target]
            if not match.empty:
                return match.iloc[0]
        except Exception:
            continue
    return None


def get_instrument_id(symbol):
    row = find_iifl_instrument(symbol)
    if row is None:
        return None, None
    details = row.replace({np.nan: None}).to_dict()
    return find_instrument_id(details), details


# ============================================================
# HISTORICAL DATA (uses the confirmed-correct lowercase key)
# ============================================================

def _call_historicaldata(instrument_id, exchange, from_date, to_date, interval):
    headers = get_iifl_headers()
    if headers is None:
        return None, "IIFL session is not available."
    url = f"{IIFL_BASE_URL}/marketdata/historicaldata"
    payload = {
        "exchange": exchange,
        "instrumentId": str(instrument_id),
        "interval": interval,
        "fromDate": from_date,
        "toDate": to_date
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
    except Exception as e:
        return None, f"Network error: {e}"

    if response.status_code == 401:
        return None, "HTTP 401 — session expired, please log in again."
    if response.status_code == 403:
        return None, "HTTP 403 — access denied (check Market Data entitlement)."
    if response.status_code != 200:
        return None, f"HTTP {response.status_code}: {response.text}"

    try:
        data = response.json()
    except Exception:
        return None, f"Invalid JSON: {response.text}"

    if data.get("status") not in ("Ok", "ok", True):
        return None, f"IIFL rejected: {data.get('message')}"

    result = data.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            pass

    candles = None
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict) and "candles" in first:
            candles = first["candles"]
        elif isinstance(first, (list, tuple)):
            candles = result
    if candles is None and isinstance(result, dict):
        for key in ["candles", "data", "result", "records"]:
            if key in result:
                candles = result[key]
                break

    if not candles:
        return None, f"Zero candles returned for exchange='{exchange}'."

    return candles, None


@st.cache_data(ttl=300, show_spinner=False)
def get_iifl_historical_data(instrument_id, from_date, to_date, interval="1 day"):
    error_log = []
    result = None
    for exchange in EXCHANGE_FALLBACKS:
        result, error = _call_historicaldata(instrument_id, exchange, from_date, to_date, interval)
        if result is not None:
            break
        error_log.append((exchange, error))

    if result is None:
        return None, error_log

    rows = []
    for candle in result:
        if isinstance(candle, (list, tuple)) and len(candle) >= 6:
            try:
                rows.append({
                    "Date": candle[0], "Open": float(candle[1]), "High": float(candle[2]),
                    "Low": float(candle[3]), "Close": float(candle[4]), "Volume": float(candle[5])
                })
            except Exception:
                continue
        elif isinstance(candle, dict):
            def gv(keys):
                for k in keys:
                    if k in candle:
                        return candle[k]
                return None
            try:
                rows.append({
                    "Date": gv(["timestamp", "time", "date"]),
                    "Open": float(gv(["open", "Open"])), "High": float(gv(["high", "High"])),
                    "Low": float(gv(["low", "Low"])), "Close": float(gv(["close", "Close"])),
                    "Volume": float(gv(["volume", "Volume"]))
                })
            except Exception:
                continue

    if not rows:
        return None, [("parsing", "Candles received but could not be parsed.")]

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df[["Open", "High", "Low", "Close", "Volume"]], []


def get_stock_daily_data(symbol, days=400):
    try:
        instrument_id, details = get_instrument_id(symbol)
        if instrument_id is None:
            return None, None, [("lookup", f"No instrument found for {symbol}.")]
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        df, errors = get_iifl_historical_data(
            instrument_id, start_date.strftime("%d-%b-%Y"), end_date.strftime("%d-%b-%Y"), "1 day"
        )
        return df, instrument_id, errors
    except Exception as e:
        return None, None, [("exception", f"{type(e).__name__}: {e}")]


def get_iifl_live_quote(instrument_id, exchange="NSEEQ"):
    headers = get_iifl_headers()
    if headers is None:
        return None, "No session."
    url = f"{IIFL_BASE_URL}/marketdata/marketquotes"
    payload = [{"exchange": exchange, "instrumentId": str(instrument_id)}]
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
    except Exception as e:
        return None, str(e)
    if response.status_code != 200:
        return None, f"HTTP {response.status_code}"
    try:
        data = response.json()
    except Exception:
        return None, "Invalid JSON"
    if data.get("status") not in ("Ok", "ok", True):
        return None, data.get("message")
    result = data.get("result")
    if isinstance(result, list) and result:
        return result[0], None
    return None, "No data"


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_atr(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def add_indicators(df):
    df = df.copy()
    df["EMA21"] = calc_ema(df["Close"], 21)
    df["EMA50"] = calc_ema(df["Close"], 50)
    df["EMA150"] = calc_ema(df["Close"], 150)
    df["EMA200"] = calc_ema(df["Close"], 200)
    df["RSI"] = calc_rsi(df["Close"], 14)
    macd, signal, hist = calc_macd(df["Close"])
    df["MACD"] = macd
    df["MACD_Signal"] = signal
    df["MACD_Hist"] = hist
    df["ATR"] = calc_atr(df, 14)
    return df


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def find_support_resistance(df, window=5, tolerance_pct=1.5, max_levels=5):
    if df is None or len(df) < window * 2 + 1:
        return [], []
    highs, lows = df["High"].values, df["Low"].values
    n = len(df)
    swing_highs, swing_lows = [], []
    for i in range(window, n - window):
        wh = highs[i - window: i + window + 1]
        wl = lows[i - window: i + window + 1]
        if highs[i] == wh.max():
            swing_highs.append(float(highs[i]))
        if lows[i] == wl.min():
            swing_lows.append(float(lows[i]))

    def cluster(levels):
        if not levels:
            return []
        levels = sorted(levels)
        clusters = [[levels[0]]]
        for lvl in levels[1:]:
            avg = np.mean(clusters[-1])
            if abs(lvl - avg) / avg * 100 <= tolerance_pct:
                clusters[-1].append(lvl)
            else:
                clusters.append([lvl])
        return [(float(np.mean(c)), len(c)) for c in clusters]

    resistance = sorted(cluster(swing_highs), key=lambda x: -x[1])[:max_levels]
    support = sorted(cluster(swing_lows), key=lambda x: -x[1])[:max_levels]
    return support, resistance


def detect_breakout(df, resistance_levels):
    if df is None or len(df) < 31 or not resistance_levels:
        return False, None
    close, prev_close = df["Close"].iloc[-1], df["Close"].iloc[-2]
    volume = df["Volume"].iloc[-1]
    avg_volume = df["Volume"].tail(30).mean()
    for price, touches in resistance_levels:
        if prev_close <= price < close:
            return True, {
                "level": price, "touches": touches,
                "volume_confirmed": bool(volume > avg_volume * 1.3),
                "volume_ratio": round(volume / avg_volume, 2) if avg_volume else 0
            }
    return False, None


# ============================================================
# VCP ANALYSIS
# ============================================================

def analyze_vcp(df):
    if df is None or len(df) < 150:
        return None

    close, volume = df["Close"], df["Volume"]
    ma50, ma150, ma200 = close.rolling(50).mean(), close.rolling(150).mean(), close.rolling(200).mean()
    current_price = float(close.iloc[-1])

    trend_score = 0
    if current_price > float(ma50.iloc[-1]): trend_score += 1
    if current_price > float(ma150.iloc[-1]): trend_score += 1
    if len(ma200.dropna()) > 0 and current_price > float(ma200.iloc[-1]): trend_score += 1
    if ma50.iloc[-1] > ma150.iloc[-1]: trend_score += 1
    if len(ma200.dropna()) > 0 and ma150.iloc[-1] > ma200.iloc[-1]: trend_score += 1

    lookback = min(120, len(close) - 1)
    prior_gain = ((current_price / float(close.iloc[-lookback])) - 1) * 100

    recent = df.tail(40)
    recent_high, recent_low = float(recent["High"].max()), float(recent["Low"].min())
    consolidation_range = ((recent_high - recent_low) / recent_high) * 100

    returns = close.pct_change()
    volatility_contracting = returns.tail(20).std() < returns.tail(60).std()

    volume_10, volume_30 = float(volume.tail(10).mean()), float(volume.tail(30).mean())
    volume_ratio = volume_10 / volume_30 if volume_30 > 0 else 1
    volume_dryup = volume_ratio < 0.85

    last_10 = df.tail(10)
    range_10 = ((float(last_10["High"].max()) - float(last_10["Low"].min())) / float(last_10["High"].max())) * 100
    tight_action = range_10 < 10

    pivot = recent_high
    distance_from_pivot = ((pivot - current_price) / pivot) * 100
    near_pivot = -2 <= distance_from_pivot <= 8

    current_volume = float(volume.iloc[-1])
    breakout_volume_ratio = current_volume / volume_30 if volume_30 > 0 else 0
    breakout_volume = breakout_volume_ratio >= 1.5

    score = 0
    score += 25 if trend_score >= 4 else 15 if trend_score >= 3 else 0
    score += 15 if prior_gain >= 20 else 8 if prior_gain >= 10 else 0
    score += 10 if consolidation_range <= 20 else 0
    score += 10 if consolidation_range <= 12 else 0
    score += 10 if volatility_contracting else 0
    score += 10 if volume_dryup else 0
    score += 5 if tight_action else 0
    score += 10 if near_pivot else 0
    score += 5 if breakout_volume else 0

    if score >= 75: signal = "STRONG VCP"
    elif score >= 60: signal = "VCP WATCH"
    elif score >= 45: signal = "DEVELOPING"
    else: signal = "NO SETUP"

    return {
        "Price": round(current_price, 2), "Score": score, "Signal": signal,
        "Trend Score": trend_score, "Prior Gain %": round(prior_gain, 2),
        "Consolidation %": round(consolidation_range, 2), "10D Range %": round(range_10, 2),
        "Volume Ratio": round(volume_ratio, 2), "Pivot": round(pivot, 2),
        "Distance Pivot %": round(distance_from_pivot, 2),
        "Breakout Vol Ratio": round(breakout_volume_ratio, 2)
    }


def signal_badge(signal):
    m = {"STRONG VCP": "badge-strong", "VCP WATCH": "badge-watch",
         "DEVELOPING": "badge-dev", "NO SETUP": "badge-none"}
    return f'<span class="signal-badge {m.get(signal, "badge-none")}">{signal}</span>'


# ============================================================
# SCANNER
# ============================================================

def scan_stocks(symbols):
    results = []
    progress = st.progress(0)
    status = st.empty()
    total = len(symbols)

    for i, symbol in enumerate(symbols):
        name = symbol.replace(".NS", "")
        status.write(f"Scanning {name} ({i + 1}/{total})")
        try:
            df, instrument_id, _ = get_stock_daily_data(symbol)
            if df is None:
                progress.progress((i + 1) / total)
                continue
            analysis = analyze_vcp(df)
            if analysis:
                support, resistance = find_support_resistance(df)
                is_breakout, breakout_info = detect_breakout(df, resistance)
                rsi = calc_rsi(df["Close"]).iloc[-1]
                atr = calc_atr(df).iloc[-1]
                analysis["Stock"] = name
                analysis["Symbol"] = symbol
                analysis["Instrument ID"] = str(instrument_id)
                analysis["RSI"] = round(float(rsi), 1)
                analysis["ATR"] = round(float(atr), 2)
                analysis["Breakout"] = "🚨 YES" if is_breakout else ""
                results.append(analysis)
        except Exception:
            pass
        progress.progress((i + 1) / total)

    progress.empty()
    status.empty()
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results).sort_values("Score", ascending=False).reset_index(drop=True)


# ============================================================
# TRADINGVIEW-STYLE CHART
# ============================================================

def render_tv_chart(symbol, df, support, resistance, live_price=None, breakout_info=None):
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        row_heights=[0.52, 0.14, 0.16, 0.18], vertical_spacing=0.02,
        specs=[[{}], [{}], [{}], [{}]]
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name=symbol, increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        increasing_fillcolor="#26a69a", decreasing_fillcolor="#ef5350"
    ), row=1, col=1)

    ema_colors = {"EMA21": "#f5c542", "EMA50": "#42a5f5", "EMA150": "#ab47bc", "EMA200": "#ff7043"}
    for ema, color in ema_colors.items():
        if ema in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[ema], name=ema, line=dict(color=color, width=1.2)
            ), row=1, col=1)

    for price, touches in resistance:
        fig.add_hline(y=price, line=dict(color="#ef5350", width=1, dash="dot"),
                       annotation_text=f"R {price:.1f}", annotation_font_size=10, row=1, col=1)
    for price, touches in support:
        fig.add_hline(y=price, line=dict(color="#26a69a", width=1, dash="dot"),
                       annotation_text=f"S {price:.1f}", annotation_font_size=10, row=1, col=1)
    if live_price:
        fig.add_hline(y=live_price, line=dict(color="#42a5f5", width=1.5),
                       annotation_text=f"LTP {live_price}", annotation_font_size=10, row=1, col=1)
    if breakout_info:
        fig.add_annotation(
            x=df.index[-1], y=df["High"].iloc[-1] * 1.02,
            text="🚨 BREAKOUT", showarrow=True, arrowhead=2,
            font=dict(color="#ff5c7a", size=12), row=1, col=1
        )

    volume_colors = np.where(df["Close"] >= df["Open"], "#26a69a", "#ef5350")
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume",
                          marker_color=volume_colors, showlegend=False), row=2, col=1)

    if "RSI" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI",
                                  line=dict(color="#f5c542", width=1.3)), row=3, col=1)
        fig.add_hline(y=70, line=dict(color="#ef5350", width=0.8, dash="dash"), row=3, col=1)
        fig.add_hline(y=30, line=dict(color="#26a69a", width=0.8, dash="dash"), row=3, col=1)

    if "MACD" in df.columns:
        macd_colors = np.where(df["MACD_Hist"] >= 0, "#26a69a", "#ef5350")
        fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], name="MACD Hist",
                              marker_color=macd_colors, showlegend=False), row=4, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD",
                                  line=dict(color="#42a5f5", width=1.2)), row=4, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"], name="Signal",
                                  line=dict(color="#ff7043", width=1.2)), row=4, col=1)

    fig.update_layout(
        height=820, template="plotly_dark",
        paper_bgcolor="#0e1117", plot_bgcolor="#131722",
        font=dict(color="#d1d4dc", size=11),
        margin=dict(l=10, r=60, t=30, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        hovermode="x unified",
        dragmode="pan",
        uirevision=symbol,  # preserves zoom/pan across reruns (e.g. live-price refresh)
        hoverlabel=dict(bgcolor="#1c2129", font_size=11, bordercolor="#2a2e39")
    )

    # Crosshair-style spikes on every axis, like TradingView
    fig.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikecolor="#758696", spikethickness=1, spikedash="solid",
        showgrid=True, gridcolor="#1e222d", zeroline=False
    )
    fig.update_yaxes(
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikecolor="#758696", spikethickness=1, spikedash="solid",
        showgrid=True, gridcolor="#1e222d", zeroline=False
    )

    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="RSI", row=3, col=1, range=[0, 100])
    fig.update_yaxes(title_text="MACD", row=4, col=1)

    # Date range selector — 1M / 3M / 6M / 1Y / All — on the top price panel
    fig.update_xaxes(
        rangeslider_visible=False,
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(step="all", label="All")
            ],
            bgcolor="#1c2129", activecolor="#2962ff",
            font=dict(color="#d1d4dc", size=10),
            x=0, y=1.08
        ),
        row=1, col=1
    )

    return fig


def render_symbol_page(symbol):
    """Full detail view: chart + indicators + S/R + VCP + breakout, for one symbol."""
    st.subheader(f"📈 {symbol.replace('.NS', '')}")

    try:
        _render_symbol_page_inner(symbol)
    except Exception as e:
        st.error(f"⚠️ Error while rendering this chart: **{type(e).__name__}**: {e}")
        with st.expander("Full traceback (for debugging)"):
            tb = traceback.format_exc()
            # Strip anything that looks like a bearer token before displaying
            session_token = st.session_state.get("iifl_user_session", "")
            if session_token:
                tb = tb.replace(session_token, "***REDACTED-TOKEN***")
            st.code(tb)


def _render_symbol_page_inner(symbol):
    with st.spinner("Loading instrument..."):
        instrument_id, details = get_instrument_id(symbol)

    if instrument_id is None:
        st.error(f"❌ Could not find instrument for {symbol}.")
        return

    with st.spinner("Loading historical data..."):
        df, _instrument_id2, errors = get_stock_daily_data(symbol)

    if df is None:
        st.error("❌ Could not load historical data.")
        with st.expander("Error details"):
            for exch, err in errors:
                st.write(f"`{exch}` → {err}")
        return

    df_ind = add_indicators(df)
    support, resistance = find_support_resistance(df)
    is_breakout, breakout_info = detect_breakout(df, resistance)
    vcp = analyze_vcp(df)

    col_refresh, col_metrics = st.columns([1, 5])
    with col_refresh:
        refresh = st.button("🔄 Refresh Live", key=f"refresh_{symbol}")

    live_price = None
    state_key = f"quote_{symbol}"
    if refresh or state_key not in st.session_state:
        quote, qerr = get_iifl_live_quote(instrument_id, "NSEEQ")
        if quote:
            st.session_state[state_key] = quote

    quote = st.session_state.get(state_key)
    if quote:
        live_price = quote.get("ltp")

    with col_metrics:
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Price", live_price or df["Close"].iloc[-1])
        m2.metric("RSI (14)", round(float(df_ind["RSI"].iloc[-1]), 1))
        m3.metric("ATR (14)", round(float(df_ind["ATR"].iloc[-1]), 2))
        m4.metric("VCP Score", vcp["Score"] if vcp else "—")
        m5.metric("Signal", vcp["Signal"] if vcp else "—")
        m6.metric("Breakout", "🚨 YES" if is_breakout else "No")

    if is_breakout and breakout_info:
        vol_note = "with volume confirmation ✅" if breakout_info["volume_confirmed"] else "on light volume ⚠️"
        st.markdown(
            f'<span class="signal-badge badge-breakout">🚨 BREAKOUT</span> '
            f'above resistance **₹{breakout_info["level"]:.1f}** ({breakout_info["touches"]} prior touches), '
            f'{vol_note} — volume {breakout_info["volume_ratio"]}x average',
            unsafe_allow_html=True
        )

    fig = render_tv_chart(symbol, df_ind, support, resistance, live_price, breakout_info)
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "scrollZoom": True,
            "displaylogo": False,
            "displayModeBar": True,
            "modeBarButtonsToRemove": [
                "select2d", "lasso2d", "autoScale2d", "toggleSpikelines"
            ],
            "modeBarButtonsToAdd": ["drawline", "eraseshape"],
            "doubleClick": "reset"
        }
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("**Resistance levels**")
        if resistance:
            st.dataframe(pd.DataFrame(resistance, columns=["Price", "Touches"]),
                         use_container_width=True, hide_index=True)
        else:
            st.caption("None detected.")
    with c2:
        st.write("**Support levels**")
        if support:
            st.dataframe(pd.DataFrame(support, columns=["Price", "Touches"]),
                         use_container_width=True, hide_index=True)
        else:
            st.caption("None detected.")
    with c3:
        st.write("**VCP details**")
        if vcp:
            st.dataframe(pd.DataFrame([vcp]).T.rename(columns={0: "Value"}),
                         use_container_width=True)
        else:
            st.caption("Not enough history (needs 150+ candles).")


# ============================================================
# SIDEBAR
# ============================================================

if "page" not in st.session_state:
    st.session_state["page"] = "🏠 Overview"
if "chart_symbol" not in st.session_state:
    st.session_state["chart_symbol"] = "RELIANCE.NS"

st.sidebar.title("📈 IIFL VCP Terminal")
st.sidebar.markdown("---")
st.sidebar.header("🔐 Connection")

if "iifl_user_session" in st.session_state:
    st.sidebar.success("🟢 Connected")
else:
    st.sidebar.error("🔴 Not connected")
    st.sidebar.link_button("🔑 Login with IIFL", IIFL_LOGIN_URL)

st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigate",
    ["🏠 Overview", "🔍 VCP Scanner", "📈 Chart Explorer"],
    index=["🏠 Overview", "🔍 VCP Scanner", "📈 Chart Explorer"].index(st.session_state["page"])
)
st.session_state["page"] = page

st.sidebar.markdown("---")
st.sidebar.header("📋 Watchlist")
watchlist_source = st.sidebar.radio(
    "Stock universe", ["Built-in F&O list (~150 stocks)", "Custom (paste symbols)"], index=0
)
if watchlist_source == "Custom (paste symbols)":
    custom_text = st.sidebar.text_area("One symbol per line", value="\n".join(FO_STOCKS[:20]), height=160)
    active_stocks = [
        s.strip().upper() if s.strip().upper().endswith(".NS") else s.strip().upper() + ".NS"
        for s in custom_text.splitlines() if s.strip()
    ]
else:
    active_stocks = FO_STOCKS
st.sidebar.caption(f"{len(active_stocks)} stocks in universe.")

# ============================================================
# PAGE: OVERVIEW
# ============================================================

if page == "🏠 Overview":
    st.title("🏠 Dashboard Overview")

    if "iifl_user_session" not in st.session_state:
        st.warning("🔴 Please log in via the sidebar to load live data.")
        st.markdown("""
        ### What this terminal does
        - **Live-ish candlestick charts** (TradingView-style, polled on demand)
        - **Automatic support & resistance** from swing-high/low clustering
        - **VCP pattern detection** (Minervini-style scoring)
        - **EMA 21/50/150/200, RSI, MACD, ATR**
        - **Breakout alerts** with volume confirmation
        - **One-click chart** for every stock your scanner finds
        """)
    else:
        st.success("🟢 Connected to IIFL — use the sidebar to scan or explore charts.")
        if "scan_results" in st.session_state and not st.session_state["scan_results"].empty:
            results = st.session_state["scan_results"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Stocks scanned", len(results))
            c2.metric("Strong VCP", int((results["Signal"] == "STRONG VCP").sum()))
            c3.metric("VCP Watch", int((results["Signal"] == "VCP WATCH").sum()))
            c4.metric("Breakouts", int((results["Breakout"] == "🚨 YES").sum()))
            st.markdown("### Top 5 setups from last scan")
            st.dataframe(results.head(5)[["Stock", "Price", "Score", "Signal", "Breakout"]],
                        use_container_width=True, hide_index=True)
        else:
            st.info("No scan results yet — run the **🔍 VCP Scanner** page first.")

# ============================================================
# PAGE: SCANNER
# ============================================================

elif page == "🔍 VCP Scanner":
    st.title("🔍 VCP Scanner")

    if "iifl_user_session" not in st.session_state:
        st.error("🔴 Please log in via the sidebar first.")
        st.stop()

    col1, col2 = st.columns([1, 3])
    with col1:
        score_filter = st.slider("Minimum VCP Score", 0, 90, 45, step=5)
        scan_button = st.button("🔍 Run Scan", type="primary")

    if scan_button:
        with st.spinner(f"Scanning {len(active_stocks)} stocks..."):
            st.session_state["scan_results"] = scan_stocks(active_stocks)

    if "scan_results" in st.session_state and not st.session_state["scan_results"].empty:
        results = st.session_state["scan_results"]
        filtered = results[results["Score"] >= score_filter]

        st.success(f"✅ {len(results)} scanned — {len(filtered)} passed filter (score ≥ {score_filter})")

        if filtered.empty:
            st.warning("No stocks meet the current score threshold.")
        else:
            st.markdown("### Results — click 📊 to open the chart")
            header = st.columns([2, 1.2, 1, 1.4, 1, 1, 1, 1])
            for h, label in zip(header, ["Stock", "Price", "Score", "Signal", "RSI", "ATR", "Breakout", ""]):
                h.markdown(f"**{label}**")

            for _, row in filtered.iterrows():
                c = st.columns([2, 1.2, 1, 1.4, 1, 1, 1, 1])
                c[0].write(row["Stock"])
                c[1].write(row["Price"])
                c[2].write(row["Score"])
                c[3].markdown(signal_badge(row["Signal"]), unsafe_allow_html=True)
                c[4].write(row["RSI"])
                c[5].write(row["ATR"])
                c[6].write(row["Breakout"] or "—")
                if c[7].button("📊", key=f"chart_btn_{row['Symbol']}"):
                    st.session_state["chart_symbol"] = row["Symbol"]
                    st.session_state["page"] = "📈 Chart Explorer"
                    st.rerun()

            csv = filtered.to_csv(index=False)
            st.download_button("⬇️ Download CSV", data=csv, file_name="vcp_watchlist.csv", mime="text/csv")

        with st.expander("📋 View all scanned stocks"):
            st.dataframe(results, use_container_width=True, hide_index=True)
    else:
        st.info("Click **🔍 Run Scan** to evaluate your watchlist.")

# ============================================================
# PAGE: CHART EXPLORER
# ============================================================

elif page == "📈 Chart Explorer":
    st.title("📈 Chart Explorer")

    if "iifl_user_session" not in st.session_state:
        st.error("🔴 Please log in via the sidebar first.")
        st.stop()

    symbol_choice = st.selectbox(
        "Symbol",
        active_stocks,
        index=active_stocks.index(st.session_state["chart_symbol"])
        if st.session_state["chart_symbol"] in active_stocks else 0
    )
    st.session_state["chart_symbol"] = symbol_choice

    render_symbol_page(symbol_choice)

# ============================================================
# FOOTER
# ============================================================

st.markdown("---")
st.caption("Educational tool only. Not investment advice. Prices are polled on demand, not streamed in real time.")
