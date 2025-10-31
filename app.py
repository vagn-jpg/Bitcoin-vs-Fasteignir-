# app.py
# Streamlit dashboard: Iceland Housing Price Index vs Bitcoin (ISK)
# Source: Yahoo Finance (yfinance) → BTC-USD × USDISK=X (falls back to ISK=X)
# Author: ChatGPT for Vagn (@vagn)

import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf
import requests

st.set_page_config(page_title="Íbúðaverð vs Bitcoin (ISK)", layout="wide")

st.title("Íbúðaverð á Íslandi vs Bitcoin (ISK)")
st.caption(
    "Samanburður frá upphafi Bitcoin. Íbúðavísitala er mánaðarleg; Bitcoin er sótt frá Yahoo Finance (BTC-USD × USD/ISK)."
    "⚙️ Engin CoinGecko notkun; við notum yfinance og gjaldmiðlapar 'USDISK=X' (með 'ISK=X' sem varaleið)."
)

# -----------------------------
# BTC í ISK frá Yahoo Finance
# -----------------------------

def fetch_btc_isk_history() -> pd.DataFrame:
    """Sækir dagleg BTC í ISK: (BTC-USD) * (USDISK=X). Skilar [date, price_isk]."""
    # BTC í USD
    btc = yf.download("BTC-USD", period="max", interval="1d", progress=False)
    if btc.empty:
        raise RuntimeError("Gat ekki sótt BTC-USD frá Yahoo Finance.")
    btc = btc.rename(columns={"Adj Close": "Adj_Close"})
    btc_usd = btc["Close"].fillna(btc.get("Adj_Close"))

    # USD/ISK gengi
    fx = yf.download("USDISK=X", period="max", interval="1d", progress=False)
    if fx.empty:
        # Varaleið: sum uppsetning notar ISK=X
        fx = yf.download("ISK=X", period="max", interval="1d", progress=False)
    if fx.empty:
        raise RuntimeError("Gat ekki sótt USD/ISK frá Yahoo Finance.")
    fx = fx.rename(columns={"Adj Close": "Adj_Close"})
    usd_isk = fx["Close"].fillna(fx.get("Adj_Close"))

    # Samræma dagsetningar
    btc_usd.index = pd.to_datetime(btc_usd.index.date)
    usd_isk.index = pd.to_datetime(usd_isk.index.date)
    df = (
        btc_usd.to_frame("btc_usd")
        .join(usd_isk.to_frame("usd_isk"), how="inner")
        .reset_index()
        .rename(columns={"index": "date"})
    )
    df["price_isk"] = df["btc_usd"] * df["usd_isk"]
    return df[["date", "price_isk"]]

@st.cache_data(ttl=24*3600)
def load_btc_isk():
    return fetch_btc_isk_history()

# ----------------------------------
# Íbúðaverðsvísitala frá PXWeb
# ----------------------------------

def _default_px_url():
    return "https://px.hagstofa.is/en/api/v1/en/Efnahagur/visitolur/1_vnv/3_greiningarvisitolur/VIS01106.px"


def fetch_housing_index_pxweb(px_url: str, from_month: str = "2009M01"):
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
            r = requests.post(px_url, json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()["data"]
            rows = []
            for d in data:
                month_label = d["key"][0]
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

@st.cache_data(ttl=24*3600)
def load_housing(px_url: str, from_month: str):
    return fetch_housing_index_pxweb(px_url, from_month=from_month)

# ----------------------------------
# Stillingar (sidebar)
# ----------------------------------
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

# ----------------------------------
# Gögn inn og umbreyting
# ----------------------------------
try:
    btc = load_btc_isk()
except Exception as e:
    st.error(f"Gat ekki sótt BTC (yfinance). {e}")
    st.stop()

if source == "PXWeb API (sjálfvirkt)":
    try:
        hpi = load_housing(px_url, from_month)
        st.success("Náði í íbúðaverðsvísitölu frá PXWeb 🎉")
    except Exception as e:
        st.error(f"Mistókst að sækja gögn frá PXWeb: {e}")
        st.stop()
else:
    if uploaded is None:
        st.warning("Hladdu upp CSV skrá til að halda áfram.")
        st.stop()
    try:
        dfu = pd.read_csv(uploaded)
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

# BTC → mánaðarlegt (meðaltal eða loka-gildi)
btc["date"] = pd.to_datetime(btc["date"])  # tryggja datetime
ym = btc["date"].dt.to_period("M")
if btc_agg == "Loka-gildi mánaðar":
    btc_m = btc.assign(ym=ym).sort_values("date").groupby("ym").tail(1).drop_duplicates("ym", keep="last")
    btc_m = btc_m[["ym","price_isk"]]
else:
    btc_m = btc.assign(ym=ym).groupby("ym", as_index=False)["price_isk"].mean()

# Samruna við vísitölu
hpi["ym"] = hpi["date"].dt.to_period("M")
df = pd.merge(hpi[["ym","hpi"]], btc_m[["ym","price_isk"]], on="ym", how="inner").sort_values("ym")
df["date"] = df["ym"].dt.to_timestamp("M")

if df.empty:
    st.error("Engin skörun milli tímaraða. Breyttu 'Byrja frá mánuði' eða athugaðu gögnin.")
    st.stop()

# Hlutföll & normalíserun
df["index_over_btc"] = df["hpi"] / df["price_isk"]
base = df.iloc[0]
df["hpi_norm"] = 100 * df["hpi"] / base["hpi"]
df["btc_norm"] = 100 * df["price_isk"] / base["price_isk"]

# ----------------------------------
# Myndrit
# ----------------------------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("Íbúðaverðsvísitala (heildarland)")
    st.plotly_chart(px.line(df, x="date", y="hpi", markers=False), use_container_width=True)
with c2:
    st.subheader("Bitcoin í ISK (Yahoo Finance)")
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

st.caption("Heimildir: Hagstofa Íslands (PXWeb) og Yahoo Finance (BTC-USD × USD/ISK). Skyndiminni: BTC 24 klst; PXWeb 24 klst.")
