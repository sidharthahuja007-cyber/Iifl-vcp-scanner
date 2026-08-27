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
    page_title="IIFL Diagnostic Tool",
    page_icon="🩺",
    layout="wide"
)

st.title("🩺 IIFL Historical-Data Diagnostic Tool")

st.caption(
    "Finds exactly which part of the IIFL pipeline is failing: "
    "login, instrument lookup, or historical-data payload."
)

# ============================================================
# CONFIG (same endpoints as the scanner app)
# ============================================================

IIFL_BASE_URL = "https://api.iiflcapital.com/v1"

IIFL_LOGIN_URL = (
    "https://markets.iiflcapital.com/"
    "?v=1&appkey=iDCmottF6T8VZr1"
)

IIFL_NSE_JSON_URL = f"{IIFL_BASE_URL}/contractfiles/NSEEQ.json"
IIFL_NSE_CSV_URL = f"{IIFL_BASE_URL}/contractfiles/NSEEQ.csv"


def mask(token, keep=4):
    """Mask a secret, keeping only the first/last `keep` chars visible."""
    if not token:
        return "None"
    token = str(token)
    if len(token) <= keep * 2:
        return "*" * len(token)
    return token[:keep] + "..." + token[-keep:] + f"  ({len(token)} chars)"


# ============================================================
# LOGIN
# ============================================================

def get_iifl_user_session(authcode, clientid):
    try:
        app_secret = st.secrets["IIFL_APP_SECRET"]
    except Exception:
        st.error("IIFL_APP_SECRET is missing from Streamlit Secrets.")
        return None

    checksum_string = str(clientid) + str(authcode) + str(app_secret)
    checksum = hashlib.sha256(checksum_string.encode("utf-8")).hexdigest()

    with st.expander("🔍 Login request diagnostics", expanded=True):
        st.write("**Checksum input (masked):**")
        st.code(
            f"clientid = {clientid}\n"
            f"authcode = {mask(authcode)}\n"
            f"app_secret = {mask(app_secret)}\n"
            f"checksum(sha256) = {checksum}"
        )

    try:
        response = requests.post(
            f"{IIFL_BASE_URL}/getusersession",
            json={"checkSum": checksum},
            timeout=30
        )
    except Exception as e:
        st.error(f"Login request could not be sent: {e}")
        return None

    with st.expander("🔍 Login response diagnostics", expanded=True):
        st.write("**HTTP status:**", response.status_code)
        st.write("**Response headers:**")
        st.json(dict(response.headers))
        st.write("**Raw response body:**")
        st.code(response.text)

    if response.status_code != 200:
        st.error(f"IIFL login HTTP error: {response.status_code}")
        return None

    try:
        data = response.json()
    except Exception:
        st.error("Login response was not valid JSON.")
        return None

    if data.get("status") == "Ok":
        session = data.get("userSession")
        if session:
            return session

    st.error("IIFL did not return a user session.")
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
# SIDEBAR — CONNECTION
# ============================================================

st.sidebar.header("🔐 IIFL Connection")

if "iifl_user_session" in st.session_state:
    st.sidebar.success("🟢 IIFL Connected")
    st.sidebar.write("**Session token (masked):**")
    st.sidebar.code(mask(st.session_state["iifl_user_session"], keep=6))
else:
    st.sidebar.error("🔴 IIFL Not Connected")
    st.sidebar.link_button("🔑 Login with IIFL", IIFL_LOGIN_URL)
    st.warning("Please log in via the sidebar before running diagnostics.")
    st.stop()

st.markdown("---")

# ============================================================
# STEP 1 — DOWNLOAD INSTRUMENT MASTER
# ============================================================

st.header("1️⃣ Download IIFL NSEEQ instrument master")

if st.button("Download instrument master now") or "instrument_df" in st.session_state:

    if "instrument_df" not in st.session_state:
        with st.spinner("Downloading contract master..."):
            df = None
            method_used = None

            try:
                r = requests.get(IIFL_NSE_JSON_URL, timeout=30)
                st.write(f"**JSON endpoint HTTP status:** {r.status_code} — `{IIFL_NSE_JSON_URL}`")
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
                        if records is None:
                            for value in raw.values():
                                if isinstance(value, list):
                                    records = value
                                    break
                    if records:
                        df = pd.DataFrame(records)
                        method_used = "JSON"
            except Exception as e:
                st.warning(f"JSON download failed: {e}")

            if df is None or df.empty:
                try:
                    r = requests.get(IIFL_NSE_CSV_URL, timeout=30)
                    st.write(f"**CSV endpoint HTTP status:** {r.status_code} — `{IIFL_NSE_CSV_URL}`")
                    if r.status_code == 200:
                        df = pd.read_csv(StringIO(r.text))
                        method_used = "CSV"
                except Exception as e:
                    st.warning(f"CSV download failed: {e}")

            st.session_state["instrument_df"] = df
            st.session_state["instrument_method"] = method_used

    df = st.session_state.get("instrument_df")
    method_used = st.session_state.get("instrument_method")

    if df is None or df.empty:
        st.error("❌ Could not download the instrument master from either endpoint.")
        st.stop()

    st.success(f"✅ Instrument master loaded via {method_used} — {len(df)} rows, {len(df.columns)} columns.")

    with st.expander("View all column names in the instrument master"):
        st.code("\n".join(str(c) for c in df.columns))

    with st.expander("Preview first 5 rows"):
        st.dataframe(df.head(), use_container_width=True)

    # ============================================================
    # STEP 2 — SEARCH FOR SYMBOL
    # ============================================================

    st.header("2️⃣ Search for a symbol")

    symbol_input = st.text_input("Enter symbol (e.g. RELIANCE, TCS, BEL)", value="RELIANCE")

    if st.button("Search instrument"):
        target = symbol_input.upper().strip().replace(".NS", "").replace("-EQ", "").replace("_EQ", "").strip()

        matches = pd.DataFrame()
        matched_column = None

        for column in df.columns:
            try:
                values = df[column].astype(str).str.upper().str.strip()
                normalized = (
                    values.str.replace(".NS", "", regex=False)
                    .str.replace("-EQ", "", regex=False)
                    .str.replace("_EQ", "", regex=False)
                    .str.replace(" EQ", "", regex=False)
                    .str.strip()
                )
                hit = df[normalized == target]
                if not hit.empty:
                    matches = hit
                    matched_column = column
                    break
            except Exception:
                continue

        if matches.empty:
            st.error(f"❌ '{target}' was not found in any column of the instrument master.")
            st.info("Try a different spelling, or check the column list above for the right field to match on.")
        else:
            record = matches.iloc[0].replace({np.nan: None}).to_dict()
            st.success(f"✅ Found '{target}' — matched on column **{matched_column}**")
            st.session_state["matched_record"] = record
            st.session_state["matched_symbol"] = target

            st.subheader("Full matched record")
            st.json(record)

            # Show every column that looks like it could be an ID
            id_like_cols = [
                k for k in record.keys()
                if any(t in k.lower().replace("_", "").replace(" ", "")
                       for t in ["instrumentid", "scripcode", "token", "securityid", "id"])
            ]

            if id_like_cols:
                st.subheader("Candidate ID fields found in this record")
                candidates_df = pd.DataFrame(
                    [{"Field": k, "Value": record[k]} for k in id_like_cols]
                )
                st.dataframe(candidates_df, use_container_width=True, hide_index=True)
            else:
                st.warning("No field with 'id' in its name was found — inspect the full record above manually.")

    # ============================================================
    # STEP 3 — TEST HISTORICAL DATA (with full auto-diagnosis)
    # ============================================================

    st.header("3️⃣ Test historical data")

    if "matched_record" not in st.session_state:
        st.info("Search for a symbol in Step 2 first.")
    else:
        record = st.session_state["matched_record"]
        id_like_cols = [
            k for k in record.keys()
            if any(t in k.lower().replace("_", "").replace(" ", "")
                   for t in ["instrumentid", "scripcode", "token", "securityid", "id"])
        ]

        col1, col2 = st.columns(2)
        with col1:
            manual_id = st.text_input(
                "Instrument ID to test (auto-filled with first candidate; edit if needed)",
                value=str(record.get(id_like_cols[0])) if id_like_cols else ""
            )
            exchange_choice = st.selectbox(
                "Exchange value to send",
                ["NSEEQ", "NSE", "N"],
                index=0
            )
        with col2:
            interval_choice = st.selectbox(
                "Interval",
                ["1 day", "1 minute", "5 minute", "15 minute", "30 minute", "60 minute"],
                index=0
            )
            days_back = st.number_input("Days of history to request", min_value=5, max_value=730, value=365)

        from_date = (datetime.now() - timedelta(days=int(days_back))).strftime("%d-%b-%Y")
        to_date = datetime.now().strftime("%d-%b-%Y")

        def call_historical(instrument_id, exchange, interval):
            headers = get_iifl_headers()
            url = f"{IIFL_BASE_URL}/marketdata/historicaldata"
            payload = {
                "exchange": exchange,
                "InstrumentId": str(instrument_id),
                "interval": interval,
                "fromDate": from_date,
                "toDate": to_date
            }
            safe_headers = dict(headers)
            safe_headers["Authorization"] = "Bearer " + mask(st.session_state["iifl_user_session"])

            result_block = {
                "payload": payload,
                "headers_sent_masked": safe_headers,
                "url": url
            }

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=30)
                result_block["http_status"] = resp.status_code
                result_block["response_headers"] = dict(resp.headers)
                result_block["raw_text"] = resp.text
                try:
                    parsed = resp.json()
                    result_block["parsed_json"] = parsed
                    result_block["api_status"] = parsed.get("status")
                    result_block["api_message"] = parsed.get("message")
                    result_block["result_len"] = (
                        len(parsed.get("result")) if isinstance(parsed.get("result"), list) else None
                    )
                except Exception:
                    result_block["parsed_json"] = None
            except Exception as e:
                result_block["exception"] = str(e)

            return result_block

        if st.button("▶️ Run single test with the settings above"):
            with st.spinner("Calling IIFL historicaldata..."):
                block = call_historical(manual_id, exchange_choice, interval_choice)

            st.subheader("Request sent")
            st.json({"url": block["url"], "payload": block["payload"], "headers": block["headers_sent_masked"]})

            if "exception" in block:
                st.error(f"❌ Request failed before a response was received: {block['exception']}")
            else:
                st.subheader("Response")
                st.write("**HTTP status:**", block["http_status"])
                with st.expander("Response headers"):
                    st.json(block["response_headers"])
                st.write("**Raw response body:**")
                st.code(block["raw_text"])

                if block.get("parsed_json") is not None:
                    st.write(f"**API status:** `{block['api_status']}`  |  **message:** `{block['api_message']}`  |  **candles returned:** {block['result_len']}")

                # ---- Diagnosis ----
                st.subheader("🩺 Diagnosis")
                if "exception" in block:
                    st.error("Network-level failure — check internet access / firewall / Streamlit Cloud egress.")
                elif block["http_status"] == 401:
                    st.error("HTTP 401 — the session token is invalid or expired. Re-login via the sidebar.")
                elif block["http_status"] == 403:
                    st.error("HTTP 403 — the account/API key may not be entitled to market data, or IP is blocked.")
                elif block["http_status"] != 200:
                    st.error(f"Unexpected HTTP status {block['http_status']} — see raw response above.")
                elif block.get("api_status") not in ("Ok", "ok", True):
                    st.error(
                        "The HTTP call succeeded but IIFL's own API returned a failure status. "
                        "This almost always means the **InstrumentId / exchange combination is wrong** "
                        "for this endpoint, even if it's the correct ID in the contract master. "
                        "Try the batch test below — it tries every candidate ID and every exchange code "
                        "automatically and tells you which combination actually works."
                    )
                elif block.get("result_len") == 0:
                    st.warning(
                        "IIFL accepted the request (status Ok) but returned zero candles. "
                        "This usually means the date range has no trading data (e.g. dates in the future, "
                        "or the instrument was newly listed) or the interval string isn't supported for this instrument."
                    )
                else:
                    st.success(f"✅ Working combination — {block['result_len']} candles returned.")

        st.markdown("---")
        st.subheader("🔁 Auto batch test (recommended)")
        st.caption(
            "Tries every ID-like field found in the matched record against every likely exchange code. "
            "Reports which exact combination IIFL accepts."
        )

        if st.button("▶️ Run batch test across all candidate IDs and exchanges"):
            if not id_like_cols:
                st.error("No candidate ID fields were found in the matched record — nothing to test.")
            else:
                exchanges_to_try = ["NSEEQ", "NSE", "N"]
                rows = []
                progress = st.progress(0)
                total = len(id_like_cols) * len(exchanges_to_try)
                i = 0

                for field in id_like_cols:
                    candidate_id = record.get(field)
                    if candidate_id in (None, "", "nan"):
                        continue
                    for exch in exchanges_to_try:
                        i += 1
                        progress.progress(i / total)
                        block = call_historical(candidate_id, exch, interval_choice)
                        rows.append({
                            "Field": field,
                            "InstrumentId tried": candidate_id,
                            "Exchange tried": exch,
                            "HTTP status": block.get("http_status", "ERR"),
                            "API status": block.get("api_status"),
                            "API message": block.get("api_message"),
                            "Candles returned": block.get("result_len"),
                            "Working?": "✅ YES" if block.get("result_len") not in (None, 0) and block.get("api_status") in ("Ok", "ok", True) else "❌ no"
                        })

                progress.empty()
                results_df = pd.DataFrame(rows)
                st.dataframe(results_df, use_container_width=True, hide_index=True)

                working = results_df[results_df["Working?"] == "✅ YES"]
                if not working.empty:
                    best = working.iloc[0]
                    st.success(
                        f"✅ Found a working combination: field **{best['Field']}** = "
                        f"`{best['InstrumentId tried']}`, exchange = `{best['Exchange tried']}`. "
                        f"Update `find_instrument_id()` in your scanner app to prefer the `{best['Field']}` "
                        f"column, and set the historical-data payload's `exchange` to `{best['Exchange tried']}`."
                    )
                else:
                    st.error(
                        "❌ None of the candidate IDs/exchanges worked. This points to one of: "
                        "(1) the session token doesn't have market-data entitlement, "
                        "(2) the account needs market-data API activation with IIFL, or "
                        "(3) the interval string used isn't supported — try switching the Interval dropdown above and re-running."
                    )
