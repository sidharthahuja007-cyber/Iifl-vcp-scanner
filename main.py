import streamlit as st
import pandas as pd
import numpy as np
import requests
import hashlib
import json
from io import StringIO
from datetime import datetime, timedelta


# ============================================================
# PAGE CONFIGURATION
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

IIFL_BASE_URL = (
    "https://api.iiflcapital.com/v1"
)

IIFL_LOGIN_URL = (
    "https://markets.iiflcapital.com/"
    "?v=1&appkey=iDCmottF6T8VZr1"
)

IIFL_NSE_CONTRACT_URL = (
    "https://api.iiflcapital.com/"
    "v1/contractfiles/NSEEQ.csv"
)


# ============================================================
# IIFL LOGIN
# ============================================================

def get_iifl_user_session(
    authcode,
    clientid
):

    try:

        # Get API secret from Streamlit Secrets
        app_secret = st.secrets[
            "IIFL_APP_SECRET"
        ]

        # ----------------------------------------------------
        # IIFL CHECKSUM
        # SHA256(clientId + authCode + API Secret)
        # ----------------------------------------------------

        checksum_string = (
            str(clientid)
            + str(authcode)
            + str(app_secret)
        )

        checksum = hashlib.sha256(
            checksum_string.encode("utf-8")
        ).hexdigest()

        # ----------------------------------------------------
        # GET USER SESSION
        # ----------------------------------------------------

        response = requests.post(
            f"{IIFL_BASE_URL}/getusersession",
            json={
                "checkSum": checksum
            },
            timeout=30
        )

        if response.status_code != 200:

            st.error(
                f"IIFL authentication HTTP error: "
                f"{response.status_code}"
            )

            st.code(
                response.text
            )

            return None

        data = response.json()

        if data.get("status") == "Ok":

            user_session = (
                data.get("userSession")
            )

            if user_session:

                return user_session

        st.error(
            "IIFL authentication failed."
        )

        st.json(data)

        return None

    except KeyError:

        st.error(
            "IIFL_APP_SECRET is missing "
            "from Streamlit Secrets."
        )

        return None

    except Exception as e:

        st.error(
            f"IIFL authentication error: {e}"
        )

        return None


# ============================================================
# READ IIFL REDIRECT
# ============================================================

query_params = st.query_params

authcode = query_params.get(
    "authcode"
)

clientid = query_params.get(
    "clientid"
)


if authcode and clientid:

    # --------------------------------------------------------
    # Generate session only if one doesn't already exist
    # --------------------------------------------------------

    if (
        "iifl_user_session"
        not in st.session_state
    ):

        with st.spinner(
            "🔐 Connecting to IIFL..."
        ):

            user_session = (
                get_iifl_user_session(
                    authcode,
                    clientid
                )
            )

        if user_session:

            st.session_state[
                "iifl_user_session"
            ] = user_session

            st.session_state[
                "iifl_client_id"
            ] = clientid

            st.success(
                "🟢 IIFL Connected Successfully"
            )

            # Remove authcode/clientid
            # from browser URL

            st.query_params.clear()

            st.rerun()


# ============================================================
# IIFL AUTHORIZATION HEADERS
# ============================================================

def get_iifl_headers():

    if (
        "iifl_user_session"
        not in st.session_state
    ):

        return None

    return {

        "Authorization": (
            "Bearer "
            + st.session_state[
                "iifl_user_session"
            ]
        ),

        "Content-Type":
            "application/json"
    }


# ============================================================
# IIFL NSE INSTRUMENT MASTER
# ============================================================

@st.cache_data(ttl=86400)
def load_iifl_nse_instruments():

    try:

        response = requests.get(
            IIFL_NSE_CONTRACT_URL,
            timeout=30
        )

        response.raise_for_status()

        # ----------------------------------------------------
        # CSV
        # ----------------------------------------------------

        df = pd.read_csv(
            StringIO(
                response.text
            )
        )

        if df.empty:

            return None

        return df

    except Exception as e:

        st.error(
            "Unable to download IIFL NSE "
            f"instrument master: {e}"
        )

        return None


# ============================================================
# FIND COLUMN
# ============================================================

def find_column(
    columns,
    candidates
):

    lower_columns = {
        str(col).lower().replace(
            "_", ""
        ).replace(
            " ", ""
        ): col
        for col in columns
    }

    for candidate in candidates:

        key = (
            candidate.lower()
            .replace("_", "")
            .replace(" ", "")
        )

        if key in lower_columns:

            return lower_columns[key]

    # Partial matching
    for col in columns:

        normalized = (
            str(col)
            .lower()
            .replace("_", "")
            .replace(" ", "")
        )

        for candidate in candidates:

            candidate_normalized = (
                candidate.lower()
                .replace("_", "")
                .replace(" ", "")
            )

            if (
                candidate_normalized
                in normalized
            ):

                return col

    return None


# ============================================================
# FIND IIFL INSTRUMENT
# ============================================================

def find_iifl_instrument(
    symbol
):

    instruments = (
        load_iifl_nse_instruments()
    )

    if instruments is None:

        return None

    clean_symbol = (
        symbol
        .replace(".NS", "")
        .replace("-EQ", "")
        .upper()
        .strip()
    )

    # --------------------------------------------------------
    # Find trading symbol column
    # --------------------------------------------------------

    symbol_column = find_column(
        instruments.columns,
        [
            "TradingSymbol",
            "tradingSymbol",
            "Symbol",
            "symbol",
            "NSETradingSymbol",
            "nseTradingSymbol"
        ]
    )

    if symbol_column is None:

        st.error(
            "Could not identify the trading "
            "symbol column in IIFL instrument master."
        )

        st.write(
            "Columns received from IIFL:"
        )

        st.write(
            list(instruments.columns)
        )

        st.dataframe(
            instruments.head(10),
            use_container_width=True
        )

        return None

    # --------------------------------------------------------
    # Normalize trading symbols
    # --------------------------------------------------------

    values = (
        instruments[
            symbol_column
        ]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    # Exact symbol
    matches = instruments[
        values == clean_symbol
    ]

    # SYMBOL-EQ
    if matches.empty:

        matches = instruments[
            values ==
            f"{clean_symbol}-EQ"
        ]

    # SYMBOL_EQ
    if matches.empty:

        matches = instruments[
            values ==
            f"{clean_symbol}_EQ"
        ]

    # Starts with symbol
    if matches.empty:

        matches = instruments[
            values.str.startswith(
                clean_symbol
            )
        ]

    if matches.empty:

        return None

    return matches.iloc[0]


# ============================================================
# GET INSTRUMENT DETAILS
# ============================================================

def get_instrument_details(
    symbol
):

    row = find_iifl_instrument(
        symbol
    )

    if row is None:

        return None

    details = {}

    for column in row.index:

        value = row[column]

        try:

            if pd.isna(value):

                value = ""

        except Exception:

            pass

        details[
            str(column)
        ] = str(value)

    return details


# ============================================================
# GET INSTRUMENT ID
# ============================================================

def get_instrument_id(
    symbol
):

    details = (
        get_instrument_details(
            symbol
        )
    )

    if details is None:

        return None, None

    # --------------------------------------------------------
    # Find instrument ID
    # --------------------------------------------------------

    instrument_id = None

    possible_id_columns = [

        "instrumentId",
        "InstrumentId",
        "InstrumentID",
        "instrumentID",
        "NSEInstrumentId",
        "nseInstrumentId"

    ]

    for key in possible_id_columns:

        if key in details:

            instrument_id = (
                details[key]
            )

            break

    return instrument_id, details


# ============================================================
# IIFL HISTORICAL DATA
# ============================================================

@st.cache_data(ttl=900)
def get_iifl_historical_data(
    instrument_id,
    from_date,
    to_date,
    interval="1 day"
):

    # --------------------------------------------------------
    # Authentication check
    # --------------------------------------------------------

    if (
        "iifl_user_session"
        not in st.session_state
    ):

        return None

    headers = get_iifl_headers()

    if headers is None:

        return None

    # --------------------------------------------------------
    # IIFL HISTORICAL ENDPOINT
    # --------------------------------------------------------

    url = (
        f"{IIFL_BASE_URL}"
        "/marketdata/historicaldata"
    )

    # --------------------------------------------------------
    # Request payload
    # --------------------------------------------------------

    payload = {

        "exchange": "NSEEQ",

        "InstrumentId": str(
            instrument_id
        ),

        "interval": interval,

        "fromDate": from_date,

        "toDate": to_date
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        # ----------------------------------------------------
        # HTTP ERROR
        # ----------------------------------------------------

        if response.status_code != 200:

            st.error(
                "IIFL historical-data HTTP "
                f"error: {response.status_code}"
            )

            st.code(
                response.text
            )

            return None

        # ----------------------------------------------------
        # Parse response
        # ----------------------------------------------------

        try:

            data = response.json()

        except Exception:

            # IIFL documentation notes that
            # historical response can be returned
            # in string format.

            try:

                data = json.loads(
                    response.text
                )

            except Exception:

                st.error(
                    "Could not decode IIFL "
                    "historical-data response."
                )

                st.code(
                    response.text
                )

                return None

        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------

        if data.get("status") != "Ok":

            st.error(
                "IIFL historical-data request failed."
            )

            st.json(data)

            return None

        result = data.get(
            "result"
        )

        # ----------------------------------------------------
        # Result can itself be a JSON string
        # ----------------------------------------------------

        if isinstance(
            result,
            str
        ):

            try:

                result = json.loads(
                    result
                )

            except Exception:

                st.error(
                    "IIFL returned an unexpected "
                    "historical-data format."
                )

                st.code(
                    result
                )

                return None

        if not result:

            return None

        # ----------------------------------------------------
        # Convert candles
        #
        # timestamp
        # open
        # high
        # low
        # close
        # volume
        # ----------------------------------------------------

        rows = []

        for candle in result:

            if not isinstance(
                candle,
                (list, tuple)
            ):

                continue

            if len(candle) < 6:

                continue

            try:

                rows.append({

                    "Date":
                        candle[0],

                    "Open":
                        float(candle[1]),

                    "High":
                        float(candle[2]),

                    "Low":
                        float(candle[3]),

                    "Close":
                        float(candle[4]),

                    "Volume":
                        float(candle[5])

                })

            except Exception:

                continue

        if not rows:

            return None

        df = pd.DataFrame(
            rows
        )

        # ----------------------------------------------------
        # Convert timestamp
        # ----------------------------------------------------

        df["Date"] = pd.to_datetime(
            df["Date"],
            errors="coerce"
        )

        df = df.dropna(
            subset=["Date"]
        )

        df = df.set_index(
            "Date"
        )

        # ----------------------------------------------------
        # Sort oldest → newest
        # ----------------------------------------------------

        df = df.sort_index()

        # ----------------------------------------------------
        # Remove duplicate candles
        # ----------------------------------------------------

        df = df[
            ~df.index.duplicated(
                keep="last"
            )
        ]

        return df[
            [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume"
            ]
        ]

    except Exception as e:

        st.error(
            f"IIFL historical-data error: {e}"
        )

        return None


# ============================================================
# VCP ANALYSIS
# ============================================================

def analyze_vcp(df):

    if (
        df is None
        or len(df) < 150
    ):

        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # --------------------------------------------------------
    # MOVING AVERAGES
    # --------------------------------------------------------

    ma50 = close.rolling(
        50
    ).mean()

    ma150 = close.rolling(
        150
    ).mean()

    ma200 = close.rolling(
        200
    ).mean()

    current_price = float(
        close.iloc[-1]
    )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    trend_score = 0

    if (
        current_price
        > float(ma50.iloc[-1])
    ):

        trend_score += 1

    if (
        current_price
        > float(ma150.iloc[-1])
    ):

        trend_score += 1

    if len(
        ma200.dropna()
    ) > 0:

        if (
            current_price
            > float(ma200.iloc[-1])
        ):

            trend_score += 1

    if (
        ma50.iloc[-1]
        > ma150.iloc[-1]
    ):

        trend_score += 1

    if len(
        ma200.dropna()
    ) > 0:

        if (
            ma150.iloc[-1]
            > ma200.iloc[-1]
        ):

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
        (
            current_price
            / old_price
        ) - 1
    ) * 100

    # --------------------------------------------------------
    # RECENT CONSOLIDATION
    # --------------------------------------------------------

    recent = df.tail(
        40
    )

    recent_high = float(
        recent["High"].max()
    )

    recent_low = float(
        recent["Low"].min()
    )

    consolidation_range = (
        (
            recent_high
            - recent_low
        )
        / recent_high
    ) * 100

    # --------------------------------------------------------
    # VOLATILITY CONTRACTION
    # --------------------------------------------------------

    returns = close.pct_change()

    volatility_20 = (
        returns.tail(20).std()
    )

    volatility_60 = (
        returns.tail(60).std()
    )

    volatility_contracting = (
        volatility_20
        < volatility_60
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
        volume_10
        / volume_30
        if volume_30 > 0
        else 1
    )

    volume_dryup = (
        volume_ratio < 0.85
    )

    # --------------------------------------------------------
    # TIGHT PRICE ACTION
    # --------------------------------------------------------

    last_10 = df.tail(
        10
    )

    high_10 = float(
        last_10["High"].max()
    )

    low_10 = float(
        last_10["Low"].min()
    )

    range_10 = (
        (
            high_10
            - low_10
        )
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
        (
            pivot
            - current_price
        )
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
        current_volume
        / volume_30
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

        "Price":
            round(
                current_price,
                2
            ),

        "Score":
            score,

        "Signal":
            signal,

        "Trend Score":
            trend_score,

        "Prior Gain %":
            round(
                prior_gain,
                2
            ),

        "Consolidation %":
            round(
                consolidation_range,
                2
            ),

        "10D Range %":
            round(
                range_10,
                2
            ),

        "Volume Ratio":
            round(
                volume_ratio,
                2
            ),

        "Pivot":
            round(
                pivot,
                2
            ),

        "Distance Pivot %":
            round(
                distance_from_pivot,
                2
            ),

        "Breakout Vol Ratio":
            round(
                breakout_volume_ratio,
                2
            )
    }


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
    "ZYDUSLIFE.NS"
]


# ============================================================
# IIFL HISTORICAL DATA FOR STOCK
# ============================================================

def get_stock_iifl_data(
    symbol
):

    instrument_id, details = (
        get_instrument_id(
            symbol
        )
    )

    if instrument_id is None:

        return None, None, details

    # --------------------------------------------------------
    # One year historical data
    # --------------------------------------------------------

    end_date = datetime.now()

    start_date = (
        end_date
        - timedelta(days=365)
    )

    from_date = (
        start_date.strftime(
            "%d-%b-%Y"
        )
    )

    to_date = (
        end_date.strftime(
            "%d-%b-%Y"
        )
    )

    df = get_iifl_historical_data(
        instrument_id=
            instrument_id,

        from_date=
            from_date,

        to_date=
            to_date,

        interval=
            "1 day"
    )

    return (
        df,
        instrument_id,
        details
    )


# ============================================================
# SCAN STOCKS USING IIFL
# ============================================================

def scan_stocks(
    symbols
):

    results = []

    progress = st.progress(
        0
    )

    status_text = st.empty()

    total = len(
        symbols
    )

    for i, symbol in enumerate(
        symbols
    ):

        clean_name = (
            symbol
            .replace(
                ".NS",
                ""
            )
        )

        status_text.write(
            f"Scanning {clean_name} "
            f"({i + 1}/{total})..."
        )

        try:

            df, instrument_id, details = (
                get_stock_iifl_data(
                    symbol
                )
            )

            if df is not None:

                analysis = analyze_vcp(
                    df
                )

                if analysis:

                    analysis[
                        "Stock"
                    ] = clean_name

                    analysis[
                        "Instrument ID"
                    ] = str(
                        instrument_id
                    )

                    results.append(
                        analysis
                    )

        except Exception as e:

            # Don't stop the entire scan
            # because one stock failed.

            continue

        progress.progress(
            (i + 1) / total
        )

    progress.empty()

    status_text.empty()

    if not results:

        return pd.DataFrame()

    result_df = pd.DataFrame(
        results
    )

    result_df = (
        result_df
        .sort_values(
            "Score",
            ascending=False
        )
        .reset_index(
            drop=True
        )
    )

    return result_df


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "🔐 IIFL Connection"
)

if (
    "iifl_user_session"
    in st.session_state
):

    st.sidebar.success(
        "🟢 IIFL Connected"
    )

else:

    st.sidebar.error(
        "🔴 IIFL Not Connected"
    )

    st.sidebar.markdown(
        "### Login"
    )

    st.sidebar.link_button(
        "🔑 Login with IIFL",
        IIFL_LOGIN_URL
    )


# ============================================================
# HISTORICAL DATA TEST
# ============================================================

st.sidebar.markdown("---")

st.sidebar.header(
    "🧪 IIFL Data Test"
)

test_symbol = st.sidebar.selectbox(
    "Select stock",
    [
        "RELIANCE.NS",
        "TCS.NS",
        "BEL.NS",
        "HAL.NS",
        "TITAN.NS",
        "HDFCBANK.NS"
    ]
)

test_instrument_button = (
    st.sidebar.button(
        "1️⃣ Test Instrument"
    )
)

test_history_button = (
    st.sidebar.button(
        "2️⃣ Test Historical Data"
    )
)


# ============================================================
# TEST INSTRUMENT
# ============================================================

if test_instrument_button:

    if (
        "iifl_user_session"
        not in st.session_state
    ):

        st.error(
            "Please login to IIFL first."
        )

    else:

        with st.spinner(
            "Finding IIFL instrument..."
        ):

            instrument_id, details = (
                get_instrument_id(
                    test_symbol
                )
            )

        if instrument_id:

            st.success(
                f"✅ {test_symbol.replace('.NS', '')} "
                "found in IIFL."
            )

            st.write(
                "IIFL Instrument ID:"
            )

            st.code(
                str(instrument_id)
            )

            st.write(
                "Instrument details:"
            )

            st.json(
                details
            )

        else:

            st.error(
                "❌ Stock could not be found "
                "in IIFL NSE instrument master."
            )

            st.info(
                "The app will display the actual "
                "IIFL columns below if the symbol "
                "column cannot be detected."
            )


# ============================================================
# TEST HISTORICAL DATA
# ============================================================

if test_history_button:

    if (
        "iifl_user_session"
        not in st.session_state
    ):

        st.error(
            "Please login to IIFL first."
        )

    else:

        with st.spinner(
            f"Finding {test_symbol.replace('.NS', '')}..."
        ):

            instrument_id, details = (
                get_instrument_id(
                    test_symbol
                )
            )

        if instrument_id:

            st.success(
                f"✅ Instrument found: "
                f"{instrument_id}"
            )

            end_date = datetime.now()

            start_date = (
                end_date
                - timedelta(days=365)
            )

            from_date = (
                start_date.strftime(
                    "%d-%b-%Y"
                )
            )

            to_date = (
                end_date.strftime(
                    "%d-%b-%Y"
                )
            )

            st.write(
                f"Requesting IIFL historical data "
                f"from {from_date} to {to_date}..."
            )

            with st.spinner(
                "Downloading IIFL daily candles..."
            ):

                historical_df = (
                    get_iifl_historical_data(
                        instrument_id=
                            instrument_id,

                        from_date=
                            from_date,

                        to_date=
                            to_date,

                        interval=
                            "1 day"
                    )
                )

            if historical_df is not None:

                st.success(
                    f"✅ IIFL returned "
                    f"{len(historical_df)} "
                    f"daily candles."
                )

                st.subheader(
                    f"📊 {test_symbol.replace('.NS', '')} "
                    "IIFL Historical Data"
                )

                st.dataframe(
                    historical_df.tail(
                        30
                    ),
                    use_container_width=True
                )

                # ------------------------------------------------
                # Test VCP engine
                # ------------------------------------------------

                if len(
                    historical_df
                ) >= 150:

                    analysis = (
                        analyze_vcp(
                            historical_df
                        )
                    )

                    if analysis:

                        st.subheader(
                            "📈 VCP Test"
                        )

                        col1, col2, col3 = (
                            st.columns(3)
                        )

                        col1.metric(
                            "Price",
                            analysis["Price"]
                        )

                        col2.metric(
                            "VCP Score",
                            analysis["Score"]
                        )

                        col3.metric(
                            "Signal",
                            analysis["Signal"]
                        )

                        st.json(
                            analysis
                        )

            else:

                st.error(
                    "❌ IIFL returned no historical data."
                )

        else:

            st.error(
                "❌ Instrument could not be found."
            )


# ============================================================
# SCANNER SETTINGS
# ============================================================

st.sidebar.markdown("---")

st.sidebar.header(
    "📊 Scanner Settings"
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
# MAIN SCANNER
# ============================================================

if scan_button:

    if (
        "iifl_user_session"
        not in st.session_state
    ):

        st.error(
            "🔴 IIFL is not connected. "
            "Please login first."
        )

        st.stop()

    with st.spinner(
        "Scanning NSE stocks using IIFL..."
    ):

        results = scan_stocks(
            NSE_STOCKS
        )

    if results.empty:

        st.error(
            "❌ No IIFL historical data "
            "was returned."
        )

        st.info(
            "Use 'Test Historical Data' "
            "with RELIANCE first."
        )

    else:

        filtered = results[
            results["Score"]
            >= score_filter
        ]

        st.success(
            f"✅ Scan completed. "
            f"{len(results)} stocks processed. "
            f"{len(filtered)} passed the "
            f"VCP score filter."
        )

        # ----------------------------------------------------
        # TOP VCP SETUPS
        # ----------------------------------------------------

        st.subheader(
            "🏆 Top VCP Setups"
        )

        if filtered.empty:

            st.warning(
                "No stocks currently meet "
                "the selected VCP score."
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
                "Instrument ID"

            ]

            available_columns = [
                col
                for col in display_columns
                if col in filtered.columns
            ]

            st.dataframe(
                filtered[
                    available_columns
                ],
                use_container_width=True,
                hide_index=True
            )

            # ------------------------------------------------
            # DOWNLOAD
            # ------------------------------------------------

            csv = filtered.to_csv(
                index=False
            )

            st.download_button(
                label=(
                    "⬇️ Download VCP Watchlist CSV"
                ),
                data=csv,
                file_name=(
                    "iifl_vcp_watchlist.csv"
                ),
                mime="text/csv"
            )

        # ----------------------------------------------------
        # ALL RESULTS
        # ----------------------------------------------------

        with st.expander(
            "📋 View all scanned stocks"
        ):

            st.dataframe(
                results,
                use_container_width=True,
                hide_index=True
            )

else:

    # --------------------------------------------------------
    # HOME SCREEN
    # --------------------------------------------------------

    if (
        "iifl_user_session"
        in st.session_state
    ):

        st.success(
            "🟢 IIFL Connected"
        )

        st.markdown(
            """
            ### IIFL Data Connection Ready

            Your scanner can now request:

            - NSE instrument IDs
            - Historical daily candles
            - Open
            - High
            - Low
            - Close
            - Volume

            Use **🧪 IIFL Data Test** in the
            sidebar before running the full scan.
            """
        )

    else:

        st.warning(
            "🔴 IIFL is not connected."
        )

        st.markdown(
            """
            ### Start here

            1. Click **Login with IIFL** in the sidebar.
            2. Complete your IIFL login.
            3. You will be redirected back here.
            4. The app will automatically generate
               your IIFL user session.
            5. Test RELIANCE historical data.
            6. Run the VCP scanner.
            """
        )

    st.markdown(
        """
        ### VCP Engine

        The scanner evaluates:

        **Trend**
        - Price vs 50/150/200-day moving averages
        - 50 MA vs 150 MA
        - 150 MA vs 200 MA

        **Prior Advance**
        - Previous price appreciation

        **Consolidation**
        - Recent 40-day range

        **Volatility Contraction**
        - 20-day vs 60-day volatility

        **Volume Dry-Up**
        - 10-day vs 30-day volume

        **Tight Price Action**
        - Recent 10-day range

        **Pivot**
        - Recent consolidation high

        **Breakout Volume**
        - Current volume vs 30-day average

        These are combined into a VCP score.
        """
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "Educational tool only. Not investment advice."
)
