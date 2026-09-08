"""
market_data.py

Handles all communication with IIFL Market APIs.

Future upgrades:
✔ Live Quotes
✔ Historical Data
✔ Instrument Master
✔ Market Breadth
✔ Index Data
"""

import requests
import pandas as pd
from io import StringIO

BASE_URL = "https://api.iiflcapital.com/v1"

# ---------------------------------------------------------
# Download Instrument Master
# ---------------------------------------------------------

def download_instrument_master():
    """
    Downloads latest NSE instrument master.
    """

    urls = [

        f"{BASE_URL}/contractfiles/NSEEQ.json",

        f"{BASE_URL}/contractfiles/NSEEQ.csv"

    ]

    for url in urls:

        try:

            r = requests.get(url, timeout=20)

            if r.status_code != 200:
                continue

            if url.endswith(".json"):

                data = r.json()

                if isinstance(data, list):

                    return pd.DataFrame(data)

                if isinstance(data, dict):

                    for key in ["result","records","data","instruments"]:

                        if key in data:

                            return pd.DataFrame(data[key])

            else:

                return pd.read_csv(StringIO(r.text))

        except:

            pass

    return None


# ---------------------------------------------------------
# Search Symbol
# ---------------------------------------------------------

def search_symbol(df, symbol):

    if df is None:

        return None

    symbol = symbol.upper().replace(".NS","")

    for col in df.columns:

        try:

            match = df[
                df[col].astype(str).str.upper() == symbol
            ]

            if not match.empty:

                return match.iloc[0]

        except:

            continue

    return None


# ---------------------------------------------------------
# Extract Instrument ID
# ---------------------------------------------------------

def instrument_id(record):

    if record is None:

        return None

    for key in [

        "instrumentId",

        "InstrumentId",

        "instrumentID",

        "instrument_id",

        "securityId",

        "token"

    ]:

        if key in record:

            return str(record[key])

    return None


# ---------------------------------------------------------
# Download Historical Candles
# ---------------------------------------------------------

def historical_data(headers,
                    instrument,
                    exchange,
                    interval,
                    from_date,
                    to_date):

    url = BASE_URL + "/marketdata/historicaldata"

    payload = {

        "exchange": exchange,

        "instrumentId": str(instrument),

        "interval": interval,

        "fromDate": from_date,

        "toDate": to_date

    }

    r = requests.post(

        url,

        headers=headers,

        json=payload,

        timeout=30

    )

    return r


# ---------------------------------------------------------
# Live Quote
# ---------------------------------------------------------

def live_quote(headers,
               instrument,
               exchange="NSEEQ"):

    url = BASE_URL + "/marketdata/marketquotes"

    payload = [

        {

            "exchange": exchange,

            "instrumentId": str(instrument)

        }

    ]

    r = requests.post(

        url,

        headers=headers,

        json=payload,

        timeout=20

    )

    return r
