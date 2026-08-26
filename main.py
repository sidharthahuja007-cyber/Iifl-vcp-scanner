import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import hashlib
import requests
from datetime import datetime, timedelta

# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="IIFL VCP Scanner",
    page_icon="📈",
    layout="wide"
)

st.title("📈 IIFL VCP Stock Scanner")
st.caption(
    "Minervini-style Volume Contraction Pattern scanner"
)

# ============================================================
# IIFL SETTINGS
# ============================================================

IIFL_BASE_URL = "https://api.iiflcapital.com/v1"

NSE_CONTRACT_URL = (
    f"{IIFL_BASE_URL}/contractfiles/NSEEQ.csv"
)


# ============================================================
# IIFL AUTHENTICATION
# ============================================================

def get_iifl_user_session(authcode, clientid):

    try:

        app_secret = st.secrets["IIFL_APP_SECRET"]

        checksum_string = (
            clientid +
            authcode +
            app_secret
        )

        checksum = hashlib.sha256(
            checksum_string.encode("utf-8")
        ).hexdigest()

        response = requests.post(
            f"{IIFL_BASE_URL}/getusersession",
            json={
                "checkSum": checksum
            },
            timeout=20
        )

        if response.status_code != 200:

            st.error(
                f"IIFL HTTP Error: "
                f"{response.status_code}"
            )

            st.code(response.text)

            return None

        data = response.json()

        if data.get("status") == "Ok":

            return data.get("userSession")

        st.error("IIFL authentication failed.")

        st.json(data)

        return None

    except Exception as e:

        st.error(
            f"IIFL authentication error: {e}"
        )

        return None


# ============================================================
# READ REDIRECT PARAMETERS
# ============================================================

query_params = st.query_params

authcode = query_params.get("authcode")
clientid = query_params.get("clientid")


if authcode and clientid:

    if "iifl_user_session" not in st.session_state:

        with st.spinner(
            "🔐 Connecting to IIFL..."
        ):

            session_token = get_iifl_user_session(
                authcode,
                clientid
            )

        if session_token:

            st.session_state[
                "iifl_user_session"
            ] = session_token

            st.session_state[
                "iifl_client_id"
            ] = clientid

            st.success(
                "✅ IIFL connected successfully!"
            )

            # Remove auth parameters from browser URL
            st.query_params.clear()

            st.rerun()


# ============================================================
# IIFL AUTH HEADER
# ============================================================

def get_iifl_headers():

    if "iifl_user_session" not in st.session_state:

        return None

    return {
        "Authorization":
            f"Bearer "
            f"{st.session_state['iifl_user_session']}",
        "Content-Type":
            "application/json"
    }


# ============================================================
# DOWNLOAD IIFL NSE INSTRUMENT MASTER
# ============================================================

@st.cache_data(ttl=86400)
def load_iifl_nse_instruments():

    try:

        response = requests.get(
            NSE_CONTRACT_URL,
            timeout=30
        )

        response.raise_for_status()

        from io import StringIO

        df = pd.read_csv(
            StringIO(response.text)
        )

        return df

    except Exception as e:

        st.error(
            f"Could not download IIFL NSE "
            f"instrument file: {e}"
        )

        return None


# ============================================================
# FIND IIFL INSTRUMENT
# ============================================================

def find_iifl_instrument(symbol):

    instruments = load_iifl_nse_instruments()

    if instruments is None:

        return None

    clean_symbol = (
        symbol
        .replace(".NS", "")
        .upper()
        .strip()
    )

    # --------------------------------------------------------
    # DISPLAY AVAILABLE COLUMN NAMES
    # --------------------------------------------------------

    possible_symbol_columns = [
        "symbol",
        "Symbol",
        "TradingSymbol",
        "tradingSymbol",
        "displayName",
        "DisplayName"
    ]

    symbol_column = None

    for col in possible_symbol_columns:

        if col in instruments.columns:

            symbol_column = col
            break

    if symbol_column is None:

        return None

    matches = instruments[
        instruments[symbol_column]
        .astype(str)
        .str.upper()
        .eq(clean_symbol)
    ]

    if matches.empty:

        return None

    return matches.iloc[0]


# ============================================================
# SHOW INSTRUMENT DETAILS
# ============================================================

def get_instrument_details(symbol):

    row = find_iifl_instrument(symbol)

    if row is None:

        return None

    details = {}

    for column in row.index:

        details[str(column)] = str(
            row[column]
        )

    return details


# ============================================================
# IIFL HISTORICAL DATA
# ============================================================

def get_iifl_historical_data(
    instrument_id,
    exchange="NSEEQ",
    from_date=None,
    to_date=None,
    interval="1D"
):

    """
    IIFL historical-data wrapper.

    IMPORTANT:
    The exact historical endpoint and request schema
    should be taken from IIFL's current API specification.

    Keep this function isolated so the rest of the VCP
    scanner does not need to change.
    """

    if "iifl_user_session" not in st.session_state:

        return None

    headers = get_iifl_headers()

    if from_date is None:

        from_date = (
            datetime.now() -
            timedelta(days=365)
        )

    if to_date is None:

        to_date = datetime.now()

    # --------------------------------------------------------
    # IMPORTANT
    # --------------------------------------------------------
    #
    # Do NOT guess the endpoint here.
    #
    # Once the exact IIFL historical endpoint is confirmed,
    # this section will make the request.
    #
    # --------------------------------------------------------

    raise NotImplementedError(
        "IIFL historical endpoint/schema "
        "needs to be confirmed from the "
        "current IIFL API specification."
    )


# ============================================================
# TEST IIFL CONNECTION
# ============================================================

def test_iifl_connection():

    if "iifl_user_session" not in st.session_state:

        return False

    headers = get_iifl_headers()

    if not headers:

        return False

    return True


# ============================================================
# TEST INSTRUMENT
# ============================================================

def test_instrument(symbol):

    details = get_instrument_details(symbol)

    return details


# ============================================================
# NSE STOCK UNIVERSE
# ============================================================

NSE_STOCKS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "ITC.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "LT.NS",
    "AXISBANK.NS",
    "KOTAKBANK.NS",
    "HINDUNILVR.NS",
    "MARUTI.NS",
    "SUNPHARMA.NS",
    "TITAN.NS",
    "BAJFINANCE.NS",
    "BAJAJFINSV.NS",
    "ADANIENT.NS",
    "ADANIPORTS.NS",
    "NTPC.NS",
    "POWERGRID.NS",
    "BEL.NS",
    "HAL.NS",
    "BHEL.NS",
    "TRENT.NS",
    "DIXON.NS",
    "CDSL.NS",
    "MCX.NS",
    "POLYCAB.NS",
    "PERSISTENT.NS",
    "COFORGE.NS",
    "JUBLFOOD.NS",
    "PIDILITIND.NS",
    "DEEPAKNTR.NS",
    "SRF.NS",
    "TATAELXSI.NS",
    "MUTHOOTFIN.NS",
    "SHRIRAMFIN.NS",
    "AUROPHARMA.NS",
    "DRREDDY.NS",
    "CIPLA.NS",
    "DIVISLAB.NS",
    "LUPIN.NS",
    "ZYDUSLIFE.NS",
]


# ============================================================
# CURRENT YAHOO DATA
# TEMPORARY FALLBACK
# ============================================================

@st.cache_data(ttl=900)
def get_yahoo_data(symbol):

    try:

        df = yf.download(
            symbol,
            period="1y",
            interval="1d",
            auto_adjust=False,
            progress=False
        )

        if df.empty:

            return None

        if isinstance(
            df.columns,
            pd.MultiIndex
        ):

            df.columns = (
                df.columns
                .get_level_values(0)
            )

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        for col in required:

            if col not in df.columns:

                return None

        return df[
            required
        ].dropna()

    except Exception:

        return None


# ============================================================
# VCP ANALYSIS
# ============================================================

def analyze_vcp(df):

    if df is None or len(df) < 150:

        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    current_price = float(
        close.iloc[-1]
    )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    trend_score = 0

    if current_price > float(
        ma50.iloc[-1]
    ):
        trend_score += 1

    if current_price > float(
        ma150.iloc[-1]
    ):
        trend_score += 1

    if len(ma200.dropna()) > 0:

        if current_price > float(
            ma200.iloc[-1]
        ):
            trend_score += 1

    if ma50.iloc[-1] > ma150.iloc[-1]:

        trend_score += 1

    if len(ma200.dropna()) > 0:

        if ma150.iloc[-1] > ma200.iloc[-1]:

            trend_score += 1

    # --------------------------------------------------------
    # PRIOR ADVANCE
    # --------------------------------------------------------

    lookback = min(
        120,
        len(close) - 1
    )

    old_price = float(
        close.iloc[-lookback]
    )

    prior_gain = (
        current_price /
        old_price - 1
    ) * 100

    # --------------------------------------------------------
    # CONSOLIDATION
    # --------------------------------------------------------

    recent = df.tail(40)

    recent_high = float(
        recent["High"].max()
    )

    recent_low = float(
        recent["Low"].min()
    )

    consolidation_range = (
        (recent_high - recent_low)
        / recent_high
    ) * 100

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    returns = close.pct_change()

    volatility_20 = (
        returns.tail(20).std()
    )

    volatility_60 = (
        returns.tail(60).std()
    )

    volatility_contracting = (
        volatility_20 <
        volatility_60
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    volume_10 = float(
        volume.tail(10).mean()
    )

    volume_30 = float(
        volume.tail(30).mean()
    )

    volume_ratio = (
        volume_10 /
        volume_30
        if volume_30 > 0
        else 1
    )

    volume_dryup = (
        volume_ratio < 0.85
    )

    # --------------------------------------------------------
    # TIGHT ACTION
    # --------------------------------------------------------

    last_10 = df.tail(10)

    high_10 = float(
        last_10["High"].max()
    )

    low_10 = float(
        last_10["Low"].min()
    )

    range_10 = (
        (high_10 - low_10)
        / high_10
    ) * 100

    tight_action = (
        range_10 < 10
    )

    # --------------------------------------------------------
    # PIVOT
    # --------------------------------------------------------

    pivot = recent_high

    distance_from_pivot = (
        (pivot - current_price)
        / pivot
    ) * 100

    near_pivot = (
        distance_from_pivot >= -2
        and distance_from_pivot <= 8
    )

    # --------------------------------------------------------
    # BREAKOUT VOLUME
    # --------------------------------------------------------

    current_volume = float(
        volume.iloc[-1]
    )

    breakout_volume_ratio = (
        current_volume /
        volume_30
        if volume_30 > 0
        else 0
    )

    breakout_volume = (
        breakout_volume_ratio >= 1.5
    )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SIGNAL
    # --------------------------------------------------------

    if score >= 75:

        signal = "STRONG VCP"

    elif score >= 60:

        signal = "VCP WATCH"

    elif score >= 45:

        signal = "DEVELOPING"

    else:

        signal = "NO SETUP"

    return {

        "Price": round(
            current_price, 2
        ),

        "Score": score,

        "Signal": signal,

        "Trend Score": trend_score,

        "Prior Gain %": round(
            prior_gain, 2
        ),

        "Consolidation %": round(
            consolidation_range, 2
        ),

        "10D Range %": round(
            range_10, 2
        ),

        "Volume Ratio": round(
            volume_ratio, 2
        ),

        "Pivot": round(
            pivot, 2
        ),

        "Distance Pivot %": round(
            distance_from_pivot, 2
        ),

        "Breakout Vol Ratio": round(
            breakout_volume_ratio, 2
        ),
    }


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("🔐 IIFL Connection")

if "iifl_user_session" in st.session_state:

    st.sidebar.success(
        "🟢 IIFL Connected"
    )

else:

    st.sidebar.warning(
        "🔴 IIFL Not Connected"
    )

st.sidebar.markdown("---")

st.sidebar.header(
    "IIFL Data Test"
)

test_symbol = st.sidebar.selectbox(
    "Test NSE Stock",
    [
        "RELIANCE.NS",
        "TCS.NS",
        "BEL.NS",
        "HAL.NS",
        "TITAN.NS"
    ]
)

test_button = st.sidebar.button(
    "🧪 Test IIFL Instrument"
)


if test_button:

    if "iifl_user_session" not in st.session_state:

        st.error(
            "Please connect IIFL first."
        )

    else:

        with st.spinner(
            "Finding IIFL instrument..."
        ):

            details = test_instrument(
                test_symbol
            )

        if details:

            st.success(
                f"✅ {test_symbol.replace('.NS', '')} "
                "found in IIFL instrument master."
            )

            st.json(details)

        else:

            st.error(
                "Stock could not be found "
                "in IIFL NSE instrument master."
            )


# ============================================================
# SCANNER SETTINGS
# ============================================================

st.sidebar.markdown("---")

st.sidebar.header(
    "Scanner Settings"
)

score_filter = st.sidebar.slider(
    "Minimum VCP Score",
    min_value=0,
    max_value=90,
    value=45,
    step=5
)

scan_button = st.sidebar.button(
    "🔍 Scan NSE Stocks"
)


# ============================================================
# MAIN
# ============================================================

if scan_button:

    st.warning(
        "⚠️ Historical IIFL candle endpoint is not "
        "connected yet. The scanner is currently "
        "using Yahoo Finance data."
    )

    results = []

    progress = st.progress(0)

    for i, symbol in enumerate(
        NSE_STOCKS
    ):

        df = get_yahoo_data(
            symbol
        )

        analysis = analyze_vcp(
            df
        )

        if analysis:

            analysis["Stock"] = (
                symbol.replace(
                    ".NS",
                    ""
                )
            )

            results.append(
                analysis
            )

        progress.progress(
            (i + 1) /
            len(NSE_STOCKS)
        )

    progress.empty()

    if results:

        result_df = pd.DataFrame(
            results
        )

        result_df = result_df.sort_values(
            "Score",
            ascending=False
        )

        filtered = result_df[
            result_df["Score"] >= score_filter
        ]

        st.success(
            f"Scan completed. "
            f"{len(filtered)} stocks passed."
        )

        st.subheader(
            "🏆 Top VCP Setups"
        )

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.error(
            "No data returned."
        )

else:

    st.info(
        "Connect IIFL and use "
        "'Test IIFL Instrument' first."
    )

    st.markdown(
        """
        ### Current status

        🟢 **IIFL authentication:** Connected

        🟢 **NSE instrument master:** Ready

        🟡 **IIFL historical candles:** Next step

        🟢 **VCP engine:** Ready

        The next step is to connect the exact
        IIFL historical-candle endpoint to the
        `get_iifl_historical_data()` function.
        """
    )

st.markdown("---")

st.caption(
    "Educational tool only. Not investment advice."
)
