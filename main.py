import streamlit as st
import pandas as pd
import numpy as np
import requests
import hashlib
import json
from datetime import datetime, timedelta
from io import StringIO

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="IIFL VCP Scanner",
    page_icon="📈",
    layout="wide"
)

st.title("📈 IIFL VCP Stock Scanner")

st.caption(
    "Minervini-style Volume Contraction Pattern scanner "
    "using IIFL historical market data"
)

# ============================================================
# IIFL CONFIGURATION
# ============================================================

IIFL_BASE_URL = "https://api.iiflcapital.com/v1"

IIFL_LOGIN_URL = (
    "https://markets.iiflcapital.com/"
    "?v=1&appkey=iDCmottF6T8VZr1"
)

IIFL_NSE_JSON_URL = f"{IIFL_BASE_URL}/contractfiles/NSEEQ.json"
IIFL_NSE_CSV_URL = f"{IIFL_BASE_URL}/contractfiles/NSEEQ.csv"

# Exchange codes to try, in priority order, when a historical-data
# call is rejected at the API level. Per IIFL docs the primary
# value is "NSEEQ"; the others are kept as automatic fallbacks in
# case of an account-specific mapping difference.
EXCHANGE_FALLBACKS = ["NSEEQ", "NSE", "N"]

NSE_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS", "AXISBANK.NS",
    "KOTAKBANK.NS", "HINDUNILVR.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "BAJFINANCE.NS", "BAJAJFINSV.NS", "ADANIENT.NS", "ADANIPORTS.NS", "NTPC.NS",
    "POWERGRID.NS", "BEL.NS", "HAL.NS", "BHEL.NS", "TRENT.NS",
    "DIXON.NS", "CDSL.NS", "MCX.NS", "POLYCAB.NS", "PERSISTENT.NS",
    "COFORGE.NS", "JUBLFOOD.NS", "PIDILITIND.NS", "DEEPAKNTR.NS", "SRF.NS",
    "TATAELXSI.NS", "MUTHOOTFIN.NS", "SHRIRAMFIN.NS", "AUROPHARMA.NS", "DRREDDY.NS",
    "CIPLA.NS", "DIVISLAB.NS", "LUPIN.NS", "ZYDUSLIFE.NS"
]

# ============================================================
# IIFL LOGIN / USER SESSION
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
            f"{IIFL_BASE_URL}/getusersession",
            json={"checkSum": checksum},
            timeout=30
        )

        if response.status_code != 200:
            st.error(f"IIFL login HTTP error: {response.status_code}")
            st.code(response.text)
            return None

        data = response.json()

        if data.get("status") == "Ok":
            session = data.get("userSession")
            if session:
                return session

        st.error("IIFL did not return a user session.")
        safe_data = dict(data)
        for key in ["userSession", "accessToken", "token"]:
            if key in safe_data:
                safe_data[key] = "***HIDDEN***"
        st.json(safe_data)
        return None

    except Exception as e:
        st.error(f"IIFL authentication error: {e}")
        return None


# ============================================================
# PROCESS REDIRECT
# ============================================================

query_params = st.query_params
authcode = query_params.get("authcode") or query_params.get("authCode")
clientid = query_params.get("clientid") or query_params.get("clientId")

if authcode and clientid and "iifl_user_session" not in st.session_state:
    with st.spinner("🔐 Connecting to IIFL..."):
        user_session = get_iifl_user_session(authcode, clientid)
    if user_session:
        st.session_state["iifl_user_session"] = user_session
        st.session_state["iifl_client_id"] = clientid
        st.session_state["iifl_connected"] = True
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
# LOAD IIFL NSE INSTRUMENT MASTER
# ============================================================

@st.cache_data(ttl=86400)
def load_iifl_nse_instruments():
    try:
        response = requests.get(IIFL_NSE_JSON_URL, timeout=30)
        if response.status_code == 200:
            raw = response.json()
            records = None
            if isinstance(raw, list):
                records = raw
            elif isinstance(raw, dict):
                for key in ["result", "data", "instruments", "records"]:
                    if key in raw and isinstance(raw[key], list):
                        records = raw[key]
                        break
                if records is None:
                    for value in raw.values():
                        if isinstance(value, list):
                            records = value
                            break
            if records:
                df = pd.DataFrame(records)
                if not df.empty:
                    return df
    except Exception:
        pass

    try:
        response = requests.get(IIFL_NSE_CSV_URL, timeout=30)
        if response.status_code == 200:
            df = pd.read_csv(StringIO(response.text))
            if not df.empty:
                return df
    except Exception:
        pass

    return None


# ============================================================
# SYMBOL / INSTRUMENT LOOKUP
# ============================================================

def normalize_symbol(symbol):
    symbol = str(symbol).upper().strip()
    return (
        symbol.replace(".NS", "").replace(".NSE", "")
        .replace("-EQ", "").replace("_EQ", "").replace(" EQ", "").strip()
    )


def find_instrument_id(record):
    if not isinstance(record, dict):
        return None
    possible_keys = [
        "instrumentId", "InstrumentId", "instrumentID", "InstrumentID",
        "instrument_id", "Instrument_Id", "NSEInstrumentId", "nseInstrumentId",
        "securityId", "SecurityId", "scripCode", "ScripCode", "token", "Token"
    ]
    for key in possible_keys:
        if key in record:
            value = record[key]
            if value is not None and str(value).strip() not in ["", "nan", "None"]:
                return str(value)
    for key, value in record.items():
        key_clean = str(key).lower().replace("_", "").replace(" ", "")
        if "instrumentid" in key_clean and value is not None:
            return str(value)
    return None


def find_iifl_instrument(symbol):
    instruments = load_iifl_nse_instruments()
    if instruments is None:
        st.error("❌ IIFL NSE instrument master could not be downloaded.")
        return None

    target = normalize_symbol(symbol)

    for column in instruments.columns:
        try:
            values = instruments[column].astype(str).str.upper().str.strip()
            normalized_values = (
                values.str.replace(".NS", "", regex=False)
                .str.replace("-EQ", "", regex=False)
                .str.replace("_EQ", "", regex=False)
                .str.replace(" EQ", "", regex=False)
                .str.strip()
            )
            match = instruments[normalized_values == target]
            if not match.empty:
                return match.iloc[0]
        except Exception:
            continue

    st.error(f"❌ {target} was not found in the IIFL NSE instrument master.")
    return None


def get_instrument_details(symbol):
    row = find_iifl_instrument(symbol)
    if row is None:
        return None
    if isinstance(row, pd.Series):
        return row.replace({np.nan: None}).to_dict()
    if isinstance(row, dict):
        return row
    return None


def get_instrument_id(symbol):
    details = get_instrument_details(symbol)
    if details is None:
        return None, None
    instrument_id = find_instrument_id(details)
    return instrument_id, details


# ============================================================
# HISTORICAL DATA — with automatic exchange fallback + transparent errors
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
        return None, f"Network error calling IIFL: {e}"

    if response.status_code == 401:
        return None, "HTTP 401 — session token invalid or expired. Please log in again."
    if response.status_code == 403:
        return None, (
            "HTTP 403 — access denied. This usually means Market Data API is not "
            "activated/entitled on this account or app key. Contact IIFL support."
        )
    if response.status_code != 200:
        return None, f"IIFL historical-data HTTP error: {response.status_code}\n{response.text}"

    try:
        data = response.json()
    except Exception:
        return None, f"IIFL returned an invalid (non-JSON) response:\n{response.text}"

    if data.get("status") not in ("Ok", "ok", True):
        message = data.get("message", "Unknown error")
        return None, (
            f"IIFL rejected the request for exchange='{exchange}': "
            f"status='{data.get('status')}', message='{message}'"
        )

    result = data.get("result")

    # The IIFL historicaldata response is documented as a string, not JSON,
    # in some deployments — handle both.
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            pass

    # Documented shape: result -> [ { "candles": [[ts,o,h,l,c,v], ...] } ]
    candles = None
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict) and "candles" in first:
            candles = first["candles"]
        elif isinstance(first, (list, tuple)):
            # already a flat list of candle rows
            candles = result

    # Fallback: some responses wrap candles inside a dict instead of a list
    if candles is None and isinstance(result, dict):
        for key in ["candles", "data", "result", "records"]:
            if key in result:
                candles = result[key]
                break

    if not candles:
        return None, (
            f"IIFL accepted the request (status Ok) for exchange='{exchange}' "
            "but returned zero candles — likely an empty date range or unsupported interval."
        )

    return candles, None


def get_iifl_historical_data(instrument_id, from_date, to_date, interval="1 day"):
    """
    Tries EXCHANGE_FALLBACKS in order. Returns (df, error_log) where
    error_log is a list of (exchange, reason) for every attempt that failed,
    so the caller can show exactly what was tried and why it didn't work.
    """
    error_log = []
    result = None

    for exchange in EXCHANGE_FALLBACKS:
        result, error = _call_historicaldata(instrument_id, exchange, from_date, to_date, interval)
        if result is not None:
            error_log.append((exchange, "✅ worked"))
            break
        else:
            error_log.append((exchange, error))

    if result is None:
        return None, error_log

    rows = []
    for candle in result:
        if isinstance(candle, (list, tuple)) and len(candle) >= 6:
            try:
                rows.append({
                    "Date": candle[0],
                    "Open": float(candle[1]),
                    "High": float(candle[2]),
                    "Low": float(candle[3]),
                    "Close": float(candle[4]),
                    "Volume": float(candle[5])
                })
            except Exception:
                continue
        elif isinstance(candle, dict):
            def get_value(keys):
                for key in keys:
                    if key in candle:
                        return candle[key]
                return None
            try:
                rows.append({
                    "Date": get_value(["timestamp", "Timestamp", "time", "Time", "date", "Date"]),
                    "Open": float(get_value(["open", "Open"])),
                    "High": float(get_value(["high", "High"])),
                    "Low": float(get_value(["low", "Low"])),
                    "Close": float(get_value(["close", "Close"])),
                    "Volume": float(get_value(["volume", "Volume"]))
                })
            except Exception:
                continue

    if not rows:
        error_log.append(("parsing", "IIFL response received but no OHLCV candles could be parsed."))
        return None, error_log

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    return df[["Open", "High", "Low", "Close", "Volume"]], error_log


def get_stock_iifl_data(symbol):
    instrument_id, details = get_instrument_id(symbol)
    if instrument_id is None:
        return None, None, details, []

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    from_date = start_date.strftime("%d-%b-%Y")
    to_date = end_date.strftime("%d-%b-%Y")

    df, error_log = get_iifl_historical_data(instrument_id, from_date, to_date, "1 day")

    return df, instrument_id, details, error_log


# ============================================================
# VCP ANALYSIS
# ============================================================

def analyze_vcp(df):
    if df is None or len(df) < 150:
        return None

    close = df["Close"]
    volume = df["Volume"]

    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    current_price = float(close.iloc[-1])

    trend_score = 0
    if current_price > float(ma50.iloc[-1]):
        trend_score += 1
    if current_price > float(ma150.iloc[-1]):
        trend_score += 1
    if len(ma200.dropna()) > 0 and current_price > float(ma200.iloc[-1]):
        trend_score += 1
    if ma50.iloc[-1] > ma150.iloc[-1]:
        trend_score += 1
    if len(ma200.dropna()) > 0 and ma150.iloc[-1] > ma200.iloc[-1]:
        trend_score += 1

    lookback = min(120, len(close) - 1)
    old_price = float(close.iloc[-lookback])
    prior_gain = ((current_price / old_price) - 1) * 100

    recent = df.tail(40)
    recent_high = float(recent["High"].max())
    recent_low = float(recent["Low"].min())
    consolidation_range = ((recent_high - recent_low) / recent_high) * 100

    returns = close.pct_change()
    volatility_20 = returns.tail(20).std()
    volatility_60 = returns.tail(60).std()
    volatility_contracting = volatility_20 < volatility_60

    volume_10 = float(volume.tail(10).mean())
    volume_30 = float(volume.tail(30).mean())
    volume_ratio = volume_10 / volume_30 if volume_30 > 0 else 1
    volume_dryup = volume_ratio < 0.85

    last_10 = df.tail(10)
    high_10 = float(last_10["High"].max())
    low_10 = float(last_10["Low"].min())
    range_10 = ((high_10 - low_10) / high_10) * 100
    tight_action = range_10 < 10

    pivot = recent_high
    distance_from_pivot = ((pivot - current_price) / pivot) * 100
    near_pivot = -2 <= distance_from_pivot <= 8

    current_volume = float(volume.iloc[-1])
    breakout_volume_ratio = current_volume / volume_30 if volume_30 > 0 else 0
    breakout_volume = breakout_volume_ratio >= 1.5

    score = 0
    if trend_score >= 4:
        score += 25
    elif trend_score >= 3:
        score += 15
    if prior_gain >= 20:
        score += 15
    elif prior_gain >= 10:
        score += 8
    if consolidation_range <= 20:
        score += 10
    if consolidation_range <= 12:
        score += 10
    if volatility_contracting:
        score += 10
    if volume_dryup:
        score += 10
    if tight_action:
        score += 5
    if near_pivot:
        score += 10
    if breakout_volume:
        score += 5

    if score >= 75:
        signal = "STRONG VCP"
    elif score >= 60:
        signal = "VCP WATCH"
    elif score >= 45:
        signal = "DEVELOPING"
    else:
        signal = "NO SETUP"

    return {
        "Price": round(current_price, 2),
        "Score": score,
        "Signal": signal,
        "Trend Score": trend_score,
        "Prior Gain %": round(prior_gain, 2),
        "Consolidation %": round(consolidation_range, 2),
        "10D Range %": round(range_10, 2),
        "Volume Ratio": round(volume_ratio, 2),
        "Pivot": round(pivot, 2),
        "Distance Pivot %": round(distance_from_pivot, 2),
        "Breakout Vol Ratio": round(breakout_volume_ratio, 2)
    }


# ============================================================
# SCAN STOCKS
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
            df, instrument_id, details, _ = get_stock_iifl_data(symbol)
            if df is None:
                progress.progress((i + 1) / total)
                continue

            analysis = analyze_vcp(df)
            if analysis:
                analysis["Stock"] = name
                analysis["Instrument ID"] = str(instrument_id)
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
# SIDEBAR — CONNECTION
# ============================================================

st.sidebar.header("🔐 IIFL Connection")

if "iifl_user_session" in st.session_state:
    st.sidebar.success("🟢 IIFL Connected")
else:
    st.sidebar.error("🔴 IIFL Not Connected")
    st.sidebar.link_button("🔑 Login with IIFL", IIFL_LOGIN_URL)

st.sidebar.markdown("---")
st.sidebar.header("🧪 IIFL Data Test")

test_symbol = st.sidebar.selectbox(
    "Select stock",
    ["RELIANCE.NS", "TCS.NS", "BEL.NS", "HAL.NS", "TITAN.NS", "HDFCBANK.NS", "INFY.NS"]
)

test_instrument = st.sidebar.button("1️⃣ Test Instrument")
test_history = st.sidebar.button("2️⃣ Test Historical Data")

# ============================================================
# TEST INSTRUMENT
# ============================================================

if test_instrument:
    if "iifl_user_session" not in st.session_state:
        st.error("Please login to IIFL first.")
    else:
        with st.spinner("Finding IIFL instrument..."):
            instrument_id, details = get_instrument_id(test_symbol)

        if instrument_id:
            st.success(f"✅ {test_symbol.replace('.NS', '')} found in IIFL.")
            st.metric("IIFL Instrument ID", str(instrument_id))
            with st.expander("View IIFL Instrument Details"):
                st.json(details)
        else:
            st.error("❌ Instrument could not be found.")

# ============================================================
# TEST HISTORICAL DATA — with full transparent error trail
# ============================================================

if test_history:
    if "iifl_user_session" not in st.session_state:
        st.error("Please login to IIFL first.")
    else:
        with st.spinner("Finding IIFL instrument..."):
            instrument_id, details = get_instrument_id(test_symbol)

        if instrument_id:
            st.success("✅ Instrument found")

            with st.spinner("Downloading IIFL historical data..."):
                historical_df, error_log = get_iifl_historical_data(
                    instrument_id,
                    (datetime.now() - timedelta(days=365)).strftime("%d-%b-%Y"),
                    datetime.now().strftime("%d-%b-%Y"),
                    "1 day"
                )

            with st.expander("🔍 What was tried (exchange fallback log)", expanded=(historical_df is None)):
                for exchange, outcome in error_log:
                    if outcome == "✅ worked":
                        st.success(f"exchange='{exchange}' → {outcome}")
                    else:
                        st.warning(f"exchange='{exchange}' → {outcome}")

            if historical_df is not None:
                st.success(f"✅ Received {len(historical_df)} daily candles.")
                st.subheader(f"📊 {test_symbol.replace('.NS', '')} Historical Data")
                st.dataframe(historical_df.tail(30), use_container_width=True)

                if len(historical_df) >= 150:
                    analysis = analyze_vcp(historical_df)
                    if analysis:
                        st.subheader("📈 VCP Analysis")
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Price", analysis["Price"])
                        col2.metric("VCP Score", analysis["Score"])
                        col3.metric("Signal", analysis["Signal"])
                        st.dataframe(pd.DataFrame([analysis]), use_container_width=True, hide_index=True)
            else:
                st.error(
                    "❌ IIFL returned no historical candles on any exchange code tried. "
                    "See the fallback log above for IIFL's exact rejection reason on each attempt. "
                    "If every attempt shows an API-level rejection (not HTTP 401/403), this points to "
                    "Market Data API not being activated/entitled on your account — confirm with IIFL support."
                )
        else:
            st.error("❌ Instrument could not be found.")

# ============================================================
# SCANNER SETTINGS
# ============================================================

st.sidebar.markdown("---")
st.sidebar.header("📊 Scanner Settings")

score_filter = st.sidebar.slider("Minimum VCP Score", min_value=0, max_value=90, value=45, step=5)
scan_button = st.sidebar.button("🔍 Scan NSE Stocks")

# ============================================================
# MAIN SCANNER
# ============================================================

if scan_button:
    if "iifl_user_session" not in st.session_state:
        st.error("🔴 IIFL is not connected.")
        st.stop()

    with st.spinner("Scanning NSE stocks using IIFL..."):
        results = scan_stocks(NSE_STOCKS)

    if results.empty:
        st.error("❌ No stocks could be processed.")
        st.info(
            "Please run '1️⃣ Test Instrument' and '2️⃣ Test Historical Data' first — "
            "the fallback log there will show IIFL's exact rejection reason."
        )
    else:
        filtered = results[results["Score"] >= score_filter]

        st.success(
            f"✅ Scan completed — {len(results)} stocks processed, "
            f"{len(filtered)} passed the filter."
        )

        st.subheader("🏆 Top VCP Setups")

        if filtered.empty:
            st.warning("No stocks currently meet the selected VCP score.")
        else:
            columns = [
                "Stock", "Price", "Score", "Signal", "Trend Score", "Prior Gain %",
                "Consolidation %", "10D Range %", "Volume Ratio", "Pivot",
                "Distance Pivot %", "Breakout Vol Ratio", "Instrument ID"
            ]
            columns = [c for c in columns if c in filtered.columns]

            st.dataframe(filtered[columns], use_container_width=True, hide_index=True)

            csv = filtered.to_csv(index=False)
            st.download_button(
                "⬇️ Download VCP Watchlist CSV",
                data=csv,
                file_name="iifl_vcp_watchlist.csv",
                mime="text/csv"
            )

        with st.expander("📋 View all scanned stocks"):
            st.dataframe(results, use_container_width=True, hide_index=True)

else:
    if "iifl_user_session" in st.session_state:
        st.success("🟢 IIFL Connected")
        st.markdown(
            """
### IIFL Connection Ready

Use the sidebar in this order:

**1️⃣ Test Instrument** — verify a symbol maps to an IIFL `instrumentId`.

**2️⃣ Test Historical Data** — verify IIFL returns daily OHLCV candles.
If this fails, expand the fallback log to see IIFL's exact rejection
reason for each exchange code tried.

**3️⃣ Scan NSE Stocks** — once the test works, run the VCP scanner.
"""
        )
    else:
        st.warning("🔴 Please login to IIFL.")
        st.markdown(
            """
### How to start

1. Click **🔑 Login with IIFL**
2. Complete your IIFL login.
3. IIFL redirects back to this app.
4. The app generates the IIFL user session.
5. Test RELIANCE.
6. Run the VCP scanner.
"""
        )

    st.markdown(
        """
### 📈 VCP Scanner

The scanner evaluates:

- Price vs 50/150/200-day moving averages
- Moving-average alignment
- Prior price advance
- 40-day consolidation
- Volatility contraction
- Volume dry-up
- 10-day price tightness
- Pivot proximity
- Breakout volume

The conditions are combined into a VCP score.
"""
    )

# ============================================================
# FOOTER
# ============================================================

st.markdown("---")
st.caption("Educational tool only. Not investment advice.")
