# app.py
# Streamlit dashboard: Iceland Housing Price Index vs Bitcoin (ISK)
# Author: ChatGPT for Vagn (@vagn)
import time
import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timezone
import plotly.express as px

st.set_page_config(page_title="Íbúðaverð vs Bitcoin (ISK)", layout="wide")

st.title("Íbúðaverð á Íslandi vs Bitcoin (ISK)")
st.caption("Samanburður frá upphafi Bitcoin. Íbúðavísitala er mánaðarleg; Bitcoin er rauntíma.\n"
           "⚙️ CoinGecko-köll eru skyndiminni-læst í 1 klst til að forðast tímabundnar villur.")

# ----------------------
# HTTP helpers með mildum retry og kurteisum hausum
# ----------------------
DEFAULT_HEADERS = {
    "User-Agent": "Iceland-Housing-vs-BTC/1.0 (Streamlit; contact: example@example.com)"
}

def http_get(url, params=None, timeout=30, tries=2, backoff=1.2):
    last_err = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=DEFAULT_HEADERS)
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            if i < tries - 1:
                time.sleep(backoff**i)
    raise last_err

def http_post(url, json_payload=None, timeout=30, tries=2, backoff=1.2):
    last_err = None
    for i in range(tries):
        try:
            r = requests.post(url, json=json_payload, timeout=timeout, headers=DEFAULT_HEADERS)
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            if i < tries - 1:
                time.sleep(backoff**i)
    raise last_err

# ----------------------
# Gögn: BTC saga + live (ISK), Íbúðaverðsvísitala frá PXWeb
# ----------------------
def fetch_btc_history_isk():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    r = http_get(url, params={"vs_currency":"isk", "days":"max"}, timeout=30)
    data = r.json()["prices"]
    df = pd.DataFrame(data, columns=["ms","price_isk"])
    # convert to Reykjavik time (UTC)
    df["date"] = pd.to_datetime(df["ms"], unit="ms", utc=True).dt.tz_convert("Atlantic/Reykjavik").dt.date
    df = df.groupby("date", as_index=False)["price_isk"].mean()
    df["date"] = pd.to_datetime(df["date"])  # normalize to midnight-naive for plotting
    return df

def fetch_btc_live_isk():
    url = "https://api.coingecko.com/api/v3/simple/price"
    r = http_get(url, params={"ids":"bitcoin","vs_currencies":"isk"}, timeout=15)
    return float(r.json()["bitcoin"]["isk"])

def _default_px_url():
    # Likleg slóð á VIS01106 (Residential property market price index).
    return "https://px.hagstofa.is/en/api/v1/en/Efnahagur/visitolur/1_vnv/3_greiningarvisitolur/VIS01106.px"

def fetch_housing_index_pxweb(px_url: str, from_month: str = "2009M01"):
    """Sækir íslenska íbúðaverðsvísitölu (heildarland). Skilar ['date','hpi'] mánaðarlega."""
    payloads = [
        {
            "query": [
                {"code": "Manudur", "selection": {"filter": "item", "values": [f"{from_month}-"]}},
                {"code": "VIST", "selection": {"filter": "item", "values": ["Heildarland"]}}
            ],
            "response": {"format": "JSON"}
        },
        {
            "query": [
                {"code": "Month", "selection": {"filter": "item", "values": [f"{from_month}-"]}},
                {"code": "VIST", "selection": {"filter": "item", "values": ["Heildarland"]}}
            ],
            "response": {"format": "JSON"}
        },
        {
            "query": [
                {"code": "Month", "selection": {"filter": "item", "values": [f"{from_month}-"]}},
                {"code": "AREA", "selection": {"filter": "item", "values": ["Whole country, total"]}}
            ],
            "response": {"format": "JSON"}
        }
    ]

    last_err = None
    for payload in payloads:
        try:
            r = http_post(px_url, json_payload=payload, timeout=30)
            data = r.json()["data"]
            rows = []
            for d in data:
                month_label = d["key"][0]  # t.d. '2025M10'
                val = float(d["values"][0])
                rows.append({"month": month_label, "hpi": val})
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["month"].str.replace("M","-") + "-01")
            df["date"] = (df["date"] + pd.offsets.MonthEnd(0))
            return df[["date","hpi"]].sort_values("date")
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"PXWeb query failed. Last error: {last_err}")

def aggregate_btc_monthly(btc_df: pd.DataFrame, method: str = "mean"):
    btc_df = btc_df.copy()
    btc_df["ym"] = btc_df["date"].dt.to_period("M")
    if method == "last":
        btc_m = btc_df.groupby("ym").tail(1)
        btc_m = btc_m[["ym","price_isk"]].drop_duplicates("ym", keep="last")
    else:
        btc_m = btc_df.groupby("ym", as_index=False)["price_isk"].mean()
    btc_m["date"] = btc_m["ym"].dt.to_timestamp("M")
    return btc_m[["date","ym","price_isk"]]

# ----------------------
# Caching / skyndiminni
# ----------------------
@st.cache_data(ttl=3600)  # 1 klst
def load_btc():
    return fetch_btc_history_isk()

@st.cache_data(ttl=3600)  # 1 klst
def load_btc_live_isk_cached():
    return fetch_btc_live_isk()

@st.cache_data(ttl=24*3600)  # 24 klst
def load_housing(px_url: str, from_month: str):
    return fetch_housing_index_pxweb(px_url, from_month=from_month)

# ----------------------
# Sidebar controls
# ----------------------
with st.sidebar:
    st.header("Stillingar")
    source = st.radio("Uppruni íbúðavísitölu", ["PXWeb API (sjálfvirkt)", "Hlaða upp CSV"], index=0)
    px_url = st.text_input("PXWeb tafla (API URL)", value=_default_px_url(),
                           help="API slóð á töflu með íbúðaverðsvísitölu. Prófaðu sjálfgefna slóð fyrst.")
    from_month = st.text_input("Byrja frá mánuði (YYYYMmm)", value="2009M01")
    btc_agg = st.selectbox("BTC mánaðarleg samantekt", ["Meðaltal dagsins", "Loka-gildi mánaðar"], index=0)
    log_btc = st.checkbox("Log-skaft á BTC", value=True)
    uploaded = None
    if source == "Hlaða upp CSV":
        uploaded = st.file_uploader("CSV með dálkunum: date (YYYY-MM-DD eða YYYY-MM) og hpi", type=["csv"])

# ----------------------
# Data loading
# ----------------------
btc = load_btc()

try:
    live = load_btc_live_isk_cached()
except Exception:
    live = None

if live is not None:
    st.info(f"Rauntíma BTC≈ISK (cached ≤1 klst): {live:,.0f} ISK")
else:
    st.info("Rauntíma BTC≈ISK: ekki tiltækt í bili (reynir aftur innan 1 klst).")

if source == "PXWeb API (sjálfvirkt)":
    try:
        hpi = load_housing(px_url, from_month)
        st.success("Náði í íbúðavísitölu frá PXWeb 🎉")
    except Exception as e:
        st.error(f"Mistókst að sækja gögn frá PXWeb: {e}")
        st.stop()
else:
    if uploaded is None:
        st.warning("Hladdu upp CSV skrá til að halda áfram.")
        st.stop()
    try:
        dfu = pd.read_csv(uploaded)
        # normalize columns
        cols = {c.lower().strip(): c for c in dfu.columns}
        date_col = cols.get("date") or cols.get("month") or list(dfu.columns)[0]
        hpi_col = cols.get("hpi") or cols.get("index") or cols.get("value") or list(dfu.columns)[1]
        hpi = pd.DataFrame({
            "date": pd.to_datetime(dfu[date_col].astype(str).str.replace("M","-") + "-01", errors="coerce").fillna(pd.to_datetime(dfu[date_col], errors="coerce")),
            "hpi": pd.to_numeric(dfu[hpi_col], errors="coerce")
        }).dropna().sort_values("date")
        hpi["date"] = (hpi["date"] + pd.offsets.MonthEnd(0))
        st.success("Upphlaðin CSV var lesin.")
    except Exception as e:
        st.error(f"Gat ekki lesið CSV: {e}")
        st.stop()

# ----------------------
# Merge + metrics
# ----------------------
btc_m = aggregate_btc_monthly(btc, method="last" if btc_agg=="Loka-gildi mánaðar" else "mean")
hpi["ym"] = hpi["date"].dt.to_period("M")
btc_m["ym"] = btc_m["date"].dt.to_period("M")
df = pd.merge(hpi[["ym","hpi"]], btc_m[["ym","price_isk"]], on="ym", how="inner").sort_values("ym")
df["date"] = df["ym"].dt.to_timestamp("M")

if df.empty:
    st.error("Engin skörun milli tímaraða. Breyttu 'Byrja frá mánuði' eða athugaðu gögnin.")
    st.stop()

df["index_over_btc"] = df["hpi"] / df["price_isk"]
base = df.iloc[0]
df["hpi_norm"] = 100 * df["hpi"] / base["hpi"]
df["btc_norm"] = 100 * df["price_isk"] / base["price_isk"]

# ----------------------
# Charts
# ----------------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("Íbúðaverðsvísitala (heildarland)")
    st.plotly_chart(px.line(df, x="date", y="hpi", markers=False), use_container_width=True)
with c2:
    st.subheader("Bitcoin í ISK")
    fig = px.line(df, x="date", y="price_isk", markers=False)
    if log_btc:
        fig.update_yaxes(type="log")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Hlutfall: Vísitala / BTC (lægra = ódýrara m.v. BTC)")
st.plotly_chart(px.line(df, x="date", y="index_over_btc"), use_container_width=True)

st.subheader("Normalíserað samanburð (=100 við fyrsta marktæka mánuð)")
st.plotly_chart(px.line(df, x="date", y=["hpi_norm","btc_norm"]), use_container_width=True)

with st.expander("Sýna gagnatöflu"):
    st.dataframe(df[["date","hpi","price_isk","index_over_btc"]].rename(columns={
        "date":"Mánuður",
        "hpi":"Íbúðaverðsvísitala",
        "price_isk":"BTC (ISK)",
        "index_over_btc":"Vísitala/BTC"
    }))

st.caption("Heimildir: Hagstofa Íslands (PXWeb) og CoinGecko API. CoinGecko-köll í þessu appi eru skyndiminni-læst (≤1 klst) til að draga úr tímabundnum villum og kvótum.")
