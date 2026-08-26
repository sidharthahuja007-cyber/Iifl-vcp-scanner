import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import hashlib
import requests

# ============================================================
# IIFL VCP STOCK SCANNER
# ============================================================

st.set_page_config(
    page_title="IIFL VCP Scanner",
    page_icon="📈",
    layout="wide"
)

st.title("📈 IIFL VCP Stock Scanner")
st.caption("Minervini-style Volume Contraction Pattern scanner for Indian stocks")


# ============================================================
# IIFL AUTHENTICATION
# ============================================================

def get_iifl_user_session(authcode, clientid):

    try:

        # Read secret from Streamlit Secrets
        app_secret = st.secrets["IIFL_APP_SECRET"]

        # ----------------------------------------------------
        # IIFL CHECKSUM
        # SHA256(clientId + authCode + AppSecret)
        # ----------------------------------------------------

        checksum_string = (
            clientid +
            authcode +
            app_secret
        )

        checksum = hashlib.sha256(
            checksum_string.encode("utf-8")
        ).hexdigest()

        # ----------------------------------------------------
        # GET USER SESSION
        # ----------------------------------------------------

        response = requests.post(
            "https://api.iiflcapital.com/v1/getusersession",
            json={
                "checkSum": checksum
            },
            timeout=20
        )

        # Check HTTP response
        if response.status_code != 200:

            st.error(
                f"IIFL server returned HTTP "
                f"{response.status_code}"
            )

            st.code(response.text)

            return None

        data = response.json()

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        if data.get("status") == "Ok":

            user_session = data.get("userSession")

            if user_session:

                return user_session

            st.error(
                "IIFL responded successfully, "
                "but userSession was not returned."
            )

            st.json(data)

            return None

        # ----------------------------------------------------
        # FAILURE
        # ----------------------------------------------------

        st.error("IIFL authentication failed.")

        st.json(data)

        return None

    except KeyError:

        st.error(
            "IIFL_APP_SECRET is missing from "
            "Streamlit Secrets."
        )

        return None

    except Exception as e:

        st.error(
            f"IIFL authentication error: {str(e)}"
        )

        return None


# ============================================================
# READ IIFL REDIRECT PARAMETERS
# ============================================================

query_params = st.query_params

authcode = query_params.get("authcode")
clientid = query_params.get("clientid")


# ============================================================
# IIFL LOGIN / SESSION
# ============================================================

if authcode and clientid:

    # Store client ID
    st.session_state["iifl_client_id"] = clientid

    # Generate session only if we don't already have one
    if "iifl_user_session" not in st.session_state:

        with st.spinner("🔐 Connecting to IIFL..."):

            user_session = get_iifl_user_session(
                authcode,
                clientid
            )

        if user_session:

            st.session_state["iifl_user_session"] = user_session

            st.success(
                "✅ IIFL connected successfully!"
            )

            # Remove auth parameters from visible URL
            st.query_params.clear()

            st.rerun()

else:

    # No IIFL redirect parameters
    pass


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
# DOWNLOAD DATA
# ============================================================

@st.cache_data(ttl=900)
def get_data(symbol):

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

        # Handle yfinance multi-index columns
        if isinstance(df.columns, pd.MultiIndex):

            df.columns = df.columns.get_level_values(0)

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

        df = df[required].dropna()

        return df

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

    # --------------------------------------------------------
    # MOVING AVERAGES
    # --------------------------------------------------------

    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    current_price = float(close.iloc[-1])

    # --------------------------------------------------------
    # TREND FILTER
    # --------------------------------------------------------

    trend_score = 0

    if current_price > float(ma50.iloc[-1]):
        trend_score += 1

    if current_price > float(ma150.iloc[-1]):
        trend_score += 1

    if len(ma200.dropna()) > 0:

        if current_price > float(ma200.iloc[-1]):
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
        (current_price / old_price) - 1
    ) * 100

    # --------------------------------------------------------
    # RECENT CONSOLIDATION
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
    # VOLATILITY CONTRACTION
    # --------------------------------------------------------

    returns = close.pct_change()

    volatility_20 = returns.tail(20).std()

    volatility_60 = returns.tail(60).std()

    volatility_contracting = (
        volatility_20 < volatility_60
    )

    # --------------------------------------------------------
    # VOLUME CONTRACTION
    # --------------------------------------------------------

    volume_10 = float(
        volume.tail(10).mean()
    )

    volume_30 = float(
        volume.tail(30).mean()
    )

    volume_ratio = (
        volume_10 / volume_30
        if volume_30 > 0
        else 1
    )

    volume_dryup = (
        volume_ratio < 0.85
    )

    # --------------------------------------------------------
    # TIGHT PRICE ACTION
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
        current_volume / volume_30
        if volume_30 > 0
        else 0
    )

    breakout_volume = (
        breakout_volume_ratio >= 1.5
    )

    # --------------------------------------------------------
    # VCP SCORE
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

        "Price": round(current_price, 2),

        "Score": score,

        "Signal": signal,

        "Trend Score": trend_score,

        "Prior Gain %": round(
            prior_gain,
            2
        ),

        "Consolidation %": round(
            consolidation_range,
            2
        ),

        "10D Range %": round(
            range_10,
            2
        ),

        "Volume Ratio": round(
            volume_ratio,
            2
        ),

        "Pivot": round(
            pivot,
            2
        ),

        "Distance Pivot %": round(
            distance_from_pivot,
            2
        ),

        "Breakout Vol Ratio": round(
            breakout_volume_ratio,
            2
        ),
    }


# ============================================================
# SCANNER
# ============================================================

def scan_stocks(symbols):

    results = []

    progress = st.progress(0)

    total = len(symbols)

    for i, symbol in enumerate(symbols):

        df = get_data(symbol)

        analysis = analyze_vcp(df)

        if analysis:

            analysis["Stock"] = symbol.replace(
                ".NS",
                ""
            )

            results.append(analysis)

        progress.progress(
            (i + 1) / total
        )

    progress.empty()

    if not results:

        return pd.DataFrame()

    result_df = pd.DataFrame(
        results
    )

    result_df = result_df.sort_values(
        "Score",
        ascending=False
    )

    return result_df


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

    st.sidebar.markdown(
        """
        Login through your IIFL login URL
        to establish an API session.
        """
    )

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

st.sidebar.markdown("---")

st.sidebar.info(
    "This scanner identifies potential VCP "
    "setups. Signals should be manually verified "
    "before trading."
)


# ============================================================
# MAIN
# ============================================================

if scan_button:

    with st.spinner(
        "Scanning NSE stocks..."
    ):

        results = scan_stocks(
            NSE_STOCKS
        )

    if results.empty:

        st.error(
            "No market data was returned. "
            "Please try again."
        )

    else:

        filtered = results[
            results["Score"] >= score_filter
        ]

        st.success(
            f"Scan completed. "
            f"{len(filtered)} stocks passed "
            f"the filter."
        )

        # ----------------------------------------------------
        # TOP SETUPS
        # ----------------------------------------------------

        st.subheader(
            "🏆 Top VCP Setups"
        )

        if filtered.empty:

            st.warning(
                "No stocks currently meet "
                "the selected score."
            )

        else:

            display_columns = [

                "Stock",
                "Price",
                "Score",
                "Signal",
                "Trend Score",
                "Prior Gain %",
                "Consolidation %",
                "10D Range %",
                "Volume Ratio",
                "Pivot",
                "Distance Pivot %",
                "Breakout Vol Ratio",

            ]

            st.dataframe(
                filtered[
                    display_columns
                ],
                use_container_width=True,
                hide_index=True
            )

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        csv = filtered.to_csv(
            index=False
        )

        st.download_button(
            label="⬇️ Download Watchlist CSV",
            data=csv,
            file_name="vcp_watchlist.csv",
            mime="text/csv"
        )

        # ----------------------------------------------------
        # ALL RESULTS
        # ----------------------------------------------------

        with st.expander(
            "View all scanned stocks"
        ):

            st.dataframe(
                results,
                use_container_width=True,
                hide_index=True
            )

else:

    if "iifl_user_session" in st.session_state:

        st.success(
            "🟢 IIFL session active. "
            "You can now run the scanner."
        )

    else:

        st.info(
            "Login to IIFL first, then return "
            "to this page."
        )

    st.markdown(
        """
        ### How this scanner works

        The scanner checks several characteristics
        associated with a Minervini-style VCP setup:

        **1. Trend**
        - Price above moving averages
        - 50-day MA
        - 150-day MA
        - 200-day MA

        **2. Prior Advance**
        - Looks for a meaningful advance before
          consolidation.

        **3. Contraction**
        - Measures recent trading range.
        - Looks for tighter price action.

        **4. Volume Dry-Up**
        - Compares recent volume with the
          previous average.

        **5. Pivot**
        - Identifies the recent consolidation high.

        **6. Breakout Volume**
        - Checks whether current volume is
          significantly above the recent average.

        **7. VCP Score**
        - Combines these conditions into a
          0–100 score.
        """
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "Educational tool only. Not investment advice."
)
