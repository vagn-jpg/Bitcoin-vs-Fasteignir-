# app.py
# Streamlit: Iceland Housing vs Bitcoin (ISK)
# Sources: CoinDesk (BTC/USD) + exchangerate.host (USD→ISK)
import streamlit as st
import pandas as pd
import plotly.express as px
import requests

st.set_page_config(page_title="Íbúðaverð vs Bitcoin (ISK)", layout="wide")

st.title("Íbúðaverð á Íslandi vs Bitcoin (ISK)")
st.caption(
    "Samanburður frá upphafi BTC (2010-07-17). BTC/USD frá CoinDesk, USD→ISK frá exchangerate.host – engir API lyklar."
)

# ---------- Helpers ----------
DEFAULT_HEADERS = {"User-Agent": "iceland-housing-vs-btc/2.0 (Render)"}

def http_get(url, params=None, timeout=30, tries=2, backoff=1.6):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            if i < tries - 1:
                import time; time.sleep(backoff**i)
    raise last

# ---------- BTC í ISK: CoinDesk + exchangerate.host ----------
def fetch_btc_isk_history(start="2010-07-17", end=None) -> pd.DataFrame:
    if end is None:
        from datetime import date
        end = str(date.today())
    # 1) BTC/USD daggildi
    r1 = http_get(
        "https://api.coindesk.com/v1/bpi/historical/close.json",
        params={"start": start, "end": end}
    )
    bpi = r1.json()["bpi"]  # { "YYYY-MM-DD": price_usd, ... }
    df_btc = pd.DataFrame(list(bpi.items()), columns=["date", "btc_usd"]).sort_values("date")
    df_btc["date"] = pd.to_datetime(df_btc["date"])

    # 2) USD→ISK daglegt gengi (timeseries)
    r2 = http_get(
        "https://api.exchangerate.host/timeseries",
        params={"start_date": start, "end_date": end, "base": "USD", "symbols": "ISK"}
    )
    rates = r2.json()
    if not rates.get("success", False):
        raise RuntimeError("exchangerate.host skilaði ekki success=true")
    rows = []
    for d, vals in rates["rates"].items():
        rows.append({"date": d, "usd_isk": vals.get("ISK")})
    df_fx = pd.DataFrame(rows).sort_values("date")
    df_fx["date"] = pd.to_datetime(df_fx["date"])
    df_fx["usd_isk"] = pd.to_numeric(df_fx["usd_isk"], errors="coerce")

    # 3) Sameina og reikna BTC í ISK
    df = pd.merge(df_btc, df_fx, on="date", how="inner")
    # Leiðrétting ef vantar gengi á einstaka daga (fylla frá næsta gildum degi)
    df["usd_isk"] = df["usd_isk"].ffill().bfill()
    df["price_isk"] = df["btc_usd"] * df["usd_isk"]
    return df[["date", "price_isk"]]

@st.cache_data(ttl=24*3600)
def load_btc_isk():
    return fetch_btc_isk_history()

# ---------- Íbúðaverðsvísitala (PXWeb) ----------
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
    last = None
    for p in payloads:
        try:
            r = http_get(px_url, timeout=30) if False else requests.post(px_url, json=p, timeout=30, headers=DEFAULT_HEADERS)
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
            last = e
            continue
    raise RuntimeError(f"PXWeb query failed. Last error: {last}")

@st.cache_data(ttl=24*3600)
def load_housing(px_url: str, from_month: str):
    return fetch_housing_index_pxweb(px_url, from_month=from_month)

# ---------- UI ----------
with st.sidebar:
    st.header("Stillingar")
    source = st.radio("Uppruni íbúðavísitölu", ["PXWeb API (sjálfvirkt)", "Hlaða upp CSV"], index=0)
    px_url = st.text_input("PXWeb tafla (API URL)", value=_default_px_url())
    from_month = st.text_input("Byrja frá mánuði (YYYYMmm)", value="2009M01")
    btc_agg = st.selectbox("BTC mánaðarleg samantekt", ["Meðaltal dagsins", "Loka-gildi mánaðar"], index=0)
    log_btc = st.checkbox("Log-skaft á BTC", value=True)
    uploaded = None
    if source == "Hlaða upp CSV":
        uploaded = st.file_uploader("CSV með dálkunum: date (YYYY-MM-DD eða YYYY-MM) og hpi", type=["csv"])

# ---------- Load data ----------
try:
    btc = load_btc_isk()
except Exception as e:
    st.error(f"Gat ekki sótt BTC (CoinDesk/exchangerate.host): {e}")
    st.stop()

if source == "PXWeb API (sjálfvirkt)":
    try:
        hpi = load_housing(px_url, from_month)
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
    except Exception as e:
        st.error(f"Gat ekki lesið CSV: {e}")
        st.stop()

# BTC → Monthly
btc["ym"] = pd.to_datetime(btc["date"]).dt.to_period("M")
if btc_agg == "Loka-gildi mánaðar":
    btc_m = btc.sort_values("date").groupby("ym").tail(1).drop_duplicates("ym", keep="last")[["ym","price_isk"]]
else:
    btc_m = btc.groupby("ym", as_index=False)["price_isk"].mean()

# Merge
hpi["ym"] = hpi["date"].dt.to_period("M")
df = pd.merge(hpi[["ym","hpi"]], btc_m[["ym","price_isk"]], on="ym", how="inner").sort_values("ym")
df["date"] = df["ym"].dt.to_timestamp("M")

if df.empty:
    st.error("Engin skörun milli tímaraða. Breyttu 'Byrja frá mánuði' eða athugaðu gögnin.")
    st.stop()

# Derived
df["index_over_btc"] = df["hpi"] / df["price_isk"]
base = df.iloc[0]
df["hpi_norm"] = 100 * df["hpi"] / base["hpi"]
df["btc_norm"] = 100 * df["price_isk"] / base["price_isk"]

# Charts
c1, c2 = st.columns(2)
with c1:
    st.subheader("Íbúðaverðsvísitala (heildarland)")
    st.plotly_chart(px.line(df, x="date", y="hpi", markers=False), use_container_width=True)
with c2:
    st.subheader("Bitcoin í ISK (CoinDesk × exchangerate.host)")
    fig = px.line(df, x="date", y="price_isk", markers=False)
    if log_btc:
        fig.update_yaxes(type="log")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Hlutfall: Vísitala / BTC (lægra = ódýrara m.v. BTC)")
st.plotly_chart(px.line(df, x="date", y="index_over_btc"), use_container_width=True)

st.subheader("Normalíserað samanburð (=100 við fyrsta marktæka mánuð)")
st.plotly_chart(px.line(df, x="date", y=["hpi_norm","btc_norm"]), use_container_width=True)

with st.expander("Sýna gagnatöflu"):
    st.dataframe(
        df[["date","hpi","price_isk","index_over_btc"]]
        .rename(columns={"date":"Mánuður","hpi":"Íbúðaverðsvísitala","price_isk":"BTC (ISK)","index_over_btc":"Vísitala/BTC"})
    )

st.caption("Heimildir: Hagstofa Íslands (PXWeb), CoinDesk (BTC/USD), exchangerate.host (USD/ISK). Cache: 24 klst.")
