"""
FinPulse Dashboard
"""

import os
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_BASE = os.environ.get("FINPULSE_API_URL", "https://algo-assignment-1.onrender.com")

st.set_page_config(page_title="FinPulse | Stock Monitor", layout="wide", page_icon=None)


# Helpers

@st.cache_data(ttl=60)
def fetch(endpoint: str):
    try:
        r = requests.get(f"{API_BASE}{endpoint}", timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Could not reach FinPulse API at {API_BASE}{endpoint}\n\n{e}")
        return None


def fmt_cr(value):
    """Format a rupee value (in raw units) into Crores for readability."""
    if value is None:
        return "-"
    return f"₹{value / 1e7:,.0f} Cr"


def color_pct(val):
    if val is None:
        return ""
    return "color: #16a34a;" if val >= 0 else "color: #dc2626;"



# SIDEBAR 

st.sidebar.title("FinPulse")

# Refresh Button 
if st.sidebar.button("Refresh live data", use_container_width=True):
    with st.spinner("Pulling fresh data from Yahoo Finance... this can take ~20s"):
        try:
            resp = requests.post(f"{API_BASE}/refresh", timeout=120)
            resp.raise_for_status()
            st.cache_data.clear()
            st.sidebar.success(f"Refreshed {resp.json().get('count', 0)} stocks")
        except Exception as e:
            st.sidebar.error(f"Refresh failed: {e}")

# Navigation 
page = st.sidebar.radio("Navigate", ["Market Overview", "Company Detail", "Comparison"])

# NEW: BONUS P/E FILTER 
st.sidebar.markdown("---")  

st.sidebar.subheader("P/E Filter (Bonus)")
min_pe = st.sidebar.slider("Min P/E", 0, 50, 0)
max_pe = st.sidebar.slider("Max P/E", 0, 100, 50)

if st.sidebar.button("Apply P/E Filter"):
    try:
        resp = requests.get(f"{API_BASE}/stocks/filter/pe?min_pe={min_pe}&max_pe={max_pe}")
        if resp.status_code == 200:
            filtered = resp.json()
            st.sidebar.success(f"Found {filtered['count']} stocks")
            
            st.session_state['filtered_stocks'] = filtered['stocks']
    except Exception as e:
        st.sidebar.error(f"Filter failed: {e}")

# API debug info 
st.sidebar.caption(f"API: `{API_BASE}`")  # <-- This is the other line you were looking for

# Data 

stocks_resp = fetch("/stocks")
stocks = stocks_resp["stocks"] if stocks_resp else []
df = pd.DataFrame(stocks)


# Market Overview Page 

if page == "Market Overview":
    st.title("Market Overview")

    summary = fetch("/market-summary")

    if summary:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Companies Tracked", summary["total_companies_tracked"])
        c2.metric("Total Market Cap", fmt_cr(summary["total_market_cap"]))
        c3.metric("Average P/E Ratio", summary["average_pe_ratio"])
        gainers_count = len([s for s in stocks if s.get("change_pct", 0) and s["change_pct"] > 0])
        c4.metric("Advancing / Declining", f"{gainers_count} / {len(stocks) - gainers_count}")

        st.markdown("### Top Movers")
        col_g, col_l = st.columns(2)

        with col_g:
            st.markdown("**Top Gainers**")
            gdf = pd.DataFrame(summary["top_gainers"])[["ticker", "name", "change_pct"]]
            st.dataframe(gdf.style.map(color_pct, subset=["change_pct"]), hide_index=True, use_container_width=True)

        with col_l:
            st.markdown("**Top Losers**")
            ldf = pd.DataFrame(summary["top_losers"])[["ticker", "name", "change_pct"]]
            st.dataframe(ldf.style.map(color_pct, subset=["change_pct"]), hide_index=True, use_container_width=True)

    st.markdown("### All Tracked Stocks")
    if not df.empty:
        display_df = df[[
            "ticker", "name", "sector", "price", "change_pct",
            "market_cap", "pe_ratio", "eps", "volume"
        ]].copy()
        display_df["market_cap"] = display_df["market_cap"].apply(fmt_cr)
        display_df.columns = ["Ticker", "Name", "Sector", "Price (₹)", "Change %",
                               "Market Cap", "P/E", "EPS", "Volume"]
        st.dataframe(
            display_df.style.map(color_pct, subset=["Change %"]),
            hide_index=True, use_container_width=True, height=600
        )
    else:
        st.info("No data yet. Click **Refresh live data** in the sidebar to pull data from Yahoo Finance.")


# Company Detail Page 

elif page == "Company Detail":
    st.title("Company Detail")

    if df.empty:
        st.info("No data yet. Click **Refresh live data** in the sidebar first.")
    else:
        options = {f"{row['ticker']} — {row['name']}": row["ticker"] for _, row in df.iterrows()}
        choice = st.selectbox("Select a company", list(options.keys()))
        ticker = options[choice]

        detail = fetch(f"/stocks/{ticker}")
        hist_resp = fetch(f"/stocks/{ticker}/history?days=180")
        hist = pd.DataFrame(hist_resp["history"]) if hist_resp else pd.DataFrame()

        if detail:
            st.subheader(f"{detail['name']} ({detail['ticker']})")
            st.caption(detail.get("sector", ""))

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Price", f"₹{detail['price']:.2f}" if detail["price"] else "-",
                      f"{detail['change_pct']}%" if detail["change_pct"] is not None else None)
            c2.metric("Market Cap", fmt_cr(detail["market_cap"]))
            c3.metric("P/E Ratio", detail["pe_ratio"])
            c4.metric("EPS", detail["eps"])
            c5.metric("P/B Ratio", detail["pb_ratio"])

            c6, c7, c8 = st.columns(3)
            c6.metric("52W High", f"₹{detail['week52_high']:.2f}" if detail["week52_high"] else "-")
            c7.metric("52W Low", f"₹{detail['week52_low']:.2f}" if detail["week52_low"] else "-")
            c8.metric("Dividend Yield", f"{detail['dividend_yield']}%" if detail["dividend_yield"] else "-")

            if not hist.empty:
                st.markdown("#### Historical Price Chart")
                fig = go.Figure(data=[go.Candlestick(
                    x=hist["date"], open=hist["open"], high=hist["high"],
                    low=hist["low"], close=hist["close"], name=ticker
                )])
                fig.update_layout(height=450, xaxis_rangeslider_visible=False,
                                   margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig, use_container_width=True)

                st.markdown("#### Volume")
                vol_fig = go.Figure(data=[go.Bar(x=hist["date"], y=hist["volume"])])
                vol_fig.update_layout(height=200, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(vol_fig, use_container_width=True)
            else:
                st.info("No historical data available yet for this ticker.")

            # NEWS SECTION 
            st.markdown("---")
            st.markdown("#### Latest News")

            try:
                news_response = fetch(f"/stocks/{ticker}/news?limit=10")
                if news_response and news_response.get("news"):
                    news_list = news_response["news"]
                    st.caption(f"Showing {len(news_list)} latest news articles.")
                    for item in news_list:
                        title = item.get("title", "No Title")
                        source = item.get("source", "Unknown")
                        link = item.get("link", "#")
                        st.markdown(f"- **[{title}]({link})**  — *{source}*")
                else:
                    st.info("No recent news found for this company.")
            except Exception as e:
                st.info("Could not fetch news at this time.")


# Comparison Page 

elif page == "Comparison":
    st.title("Company Comparison")

    if df.empty:
        st.info("No data yet. Click **Refresh live data** in the sidebar first.")
    else:
        # Sector Filter Dropdown 
        sectors = sorted(df["sector"].dropna().unique())
        sector_options = ["All Sectors"] + sectors
        selected_sector = st.selectbox("Filter companies by sector", sector_options)
        
        # Filter the dataframe based on selected sector
        if selected_sector != "All Sectors":
            filtered_df = df[df["sector"] == selected_sector]
        else:
            filtered_df = df
        
        # Create options for the multiselect
        options = {f"{row['ticker']} — {row['name']}": row["ticker"] for _, row in filtered_df.iterrows()}
        
        # Show count of available stocks
        st.caption(f"Showing {len(options)} stocks in '{selected_sector}'")
        
        selected = st.multiselect(
            "Select companies to compare (2-6 recommended)",
            list(options.keys()),
            default=list(options.keys())[:min(3, len(options))]
        )
        tickers = [options[s] for s in selected]

        if tickers:
            comp_rows = [detail for t in tickers if (detail := fetch(f"/stocks/{t}"))]
            comp_df = pd.DataFrame(comp_rows)[[
                "ticker", "name", "price", "change_pct", "market_cap",
                "pe_ratio", "eps", "pb_ratio", "dividend_yield"
            ]]
            comp_df["market_cap"] = comp_df["market_cap"].apply(fmt_cr)
            st.dataframe(comp_df, hide_index=True, use_container_width=True)

            st.markdown("#### Normalized Price Trend (Last 180 Days, rebased to 100)")
            fig = go.Figure()
            for t in tickers:
                h = fetch(f"/stocks/{t}/history?days=180")
                if h and h["history"]:
                    hdf = pd.DataFrame(h["history"])
                    if not hdf.empty and "close" in hdf.columns:
                        base = hdf["close"].iloc[0]
                        fig.add_trace(go.Scatter(
                            x=hdf["date"], y=(hdf["close"] / base) * 100,
                            mode="lines", name=t
                        ))
            fig.update_layout(height=450, yaxis_title="Rebased Price (Base=100)",
                               margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### P/E Ratio Comparison")
            pe_fig = go.Figure(data=[go.Bar(
                x=comp_df["ticker"], y=[r["pe_ratio"] for r in comp_rows if r["pe_ratio"] is not None]
            )])
            pe_fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(pe_fig, use_container_width=True)
        else:
            st.info("Select at least one company to compare.")
