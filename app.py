# ---------- BTC í ISK: Multi-source + offline fallback ----------
import io

DEFAULT_HEADERS = {"User-Agent": "iceland-housing-vs-btc/2.1 (Render)"}

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

def fetch_btc_isk_history_online(start="2010-07-17", end=None) -> pd.DataFrame:
    """Reynir fyrst CoinDesk (BTC/USD) + exchangerate.host (USD/ISK).
       Skilar df[date, price_isk] eða kastar villu ef netið bilar."""
    if end is None:
        from datetime import date
        end = str(date.today())
    # 1) BTC/USD (CoinDesk)
    r1 = http_get(
        "https://api.coindesk.com/v1/bpi/historical/close.json",
        params={"start": start, "end": end}
    )
    bpi = r1.json()["bpi"]  # {YYYY-MM-DD: price_usd}
    df_btc = pd.DataFrame(list(bpi.items()), columns=["date", "btc_usd"]).sort_values("date")
    df_btc["date"] = pd.to_datetime(df_btc["date"])
    # 2) USD/ISK (exchangerate.host)
    r2 = http_get(
        "https://api.exchangerate.host/timeseries",
        params={"start_date": start, "end_date": end, "base": "USD", "symbols": "ISK"}
    )
    rates = r2.json()
    if not rates.get("success", False):
        raise RuntimeError("exchangerate.host skilaði ekki success=true")
    df_fx = (
        pd.DataFrame(
            [{"date": d, "usd_isk": vals.get("ISK")} for d, vals in rates["rates"].items()]
        )
        .sort_values("date")
    )
    df_fx["date"] = pd.to_datetime(df_fx["date"])
    df_fx["usd_isk"] = pd.to_numeric(df_fx["usd_isk"], errors="coerce").ffill().bfill()
    # 3) Merge → ISK
    df = pd.merge(df_btc, df_fx, on="date", how="inner")
    df["price_isk"] = df["btc_usd"] * df["usd_isk"]
    return df[["date", "price_isk"]]

@st.cache_data(ttl=24*3600)
def load_btc_isk_online():
    return fetch_btc_isk_history_online()

def load_btc_isk_with_fallback():
    """Reynir net. Ef það bilar, biður um CSV og heldur áfram."""
    try:
        return load_btc_isk_online()
    except Exception as e:
        st.warning(
            "Tókst ekki að sækja BTC söguna á netinu (t.d. DNS á hýsingunni). "
            "Hladdu inn CSV skránni með dálkum: `date,price_isk` til að halda áfram.\n\n"
            f"Nánar: {e}"
        )
        btc_csv = st.file_uploader("Hlaða upp BTC-ISK sögu (CSV)", type=["csv"], key="btc_csv_fallback")
        if btc_csv is None:
            st.stop()
        try:
            dfu = pd.read_csv(btc_csv)
            # væntum: date,price_isk (case-insensitive fallb.)
            cols = {c.lower().strip(): c for c in dfu.columns}
            date_col = cols.get("date") or list(dfu.columns)[0]
            price_col = cols.get("price_isk") or cols.get("price") or list(dfu.columns)[1]
            df = pd.DataFrame({
                "date": pd.to_datetime(dfu[date_col], errors="coerce"),
                "price_isk": pd.to_numeric(dfu[price_col], errors="coerce")
            }).dropna().sort_values("date")
            if df.empty:
                raise ValueError("CSV tómt eða ógilt")
            return df
        except Exception as e2:
            st.error(f"Ekki tókst að lesa BTC CSV: {e2}")
            st.stop()
