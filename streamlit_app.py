import streamlit as st
import requests
import pandas as pd
import altair as alt

FASTAPI_URL = "https://web-production-c5eac.up.railway.app/backtest_mvp"

st.set_page_config(page_title="AI Backtester", layout="wide")
st.title("📈 SPY Rolling Strategy Backtester")

# === Sidebar Inputs ===
ticker = st.sidebar.text_input("Ticker", "SPY")

# Contract-based input
contracts = st.sidebar.number_input(
    "Number of Contracts (1 contract = 100 SPY shares)",
    min_value=1,
    max_value=10,
    value=2,
    step=1
)
shares = contracts * 100
st.sidebar.write(f"👉 This backtest will assume you own **{shares} SPY shares**.")

strategy = st.sidebar.selectbox(
    "Select Strategy",
    [
        "rolling_atm_puts",
        "rolling_otm_puts",
        "rolling_put_spread",
        "rolling_collar",
        "rolling_zero_cost_collar"
    ]
)

# Optional strategy parameters
otm_percent = None
spread_width_percent = None
upside_cap_percent = None
coverage_ratio = None

if strategy == "rolling_otm_puts":
    otm_percent = st.sidebar.slider("OTM % for puts", 1.0, 15.0, 5.0)
elif strategy == "rolling_put_spread":
    spread_width_percent = st.sidebar.slider("Put Spread Width %", 1.0, 15.0, 5.0)
elif strategy == "rolling_collar":
    upside_cap_percent = st.sidebar.slider("Upside Cap %", 2.0, 25.0, 10.0)
elif strategy == "rolling_zero_cost_collar":
    coverage_ratio = st.sidebar.slider(
        "Coverage ratio (1.0 = full offset, <1 = partial)",
        0.5, 1.2, 1.0, step=0.05
    )

# === Helper function to run one strategy ===
def run_strategy(strategy_name, shares):
    payload = {"ticker": ticker, "shares": shares, "strategy": strategy_name}
    if strategy_name == "rolling_otm_puts":
        payload["otm_percent"] = otm_percent or 5
    elif strategy_name == "rolling_put_spread":
        payload["spread_width_percent"] = spread_width_percent or 5
    elif strategy_name == "rolling_collar":
        payload["upside_cap_percent"] = upside_cap_percent or 10
    elif strategy_name == "rolling_zero_cost_collar":
        payload["coverage_ratio"] = coverage_ratio or 1.0

    resp = requests.post(FASTAPI_URL, json=payload)
    return resp.json() if resp.status_code == 200 else None

# === Helper: Buy & Hold baseline metrics ===
def run_buy_and_hold(shares):
    # Call any strategy (ATM) but only use stock_pnl
    payload = {"ticker": ticker, "shares": shares, "strategy": "rolling_atm_puts"}
    resp = requests.post(FASTAPI_URL, json=payload)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if "results" not in data:
        return None

    df = pd.DataFrame(data["results"])
    monthly_stock = df["stock_pnl"].tolist()

    total_stock_pl = sum(monthly_stock)
    cum_stock = df["stock_pnl"].cumsum()
    running_max = cum_stock.cummax()
    drawdowns = running_max - cum_stock
    max_drawdown = drawdowns.max()
    vol = df["stock_pnl"].std()
    avg_monthly = df["stock_pnl"].mean()
    risk_adj = avg_monthly / vol if vol > 0 else 0

    return {
        "Strategy": "Buy & Hold",
        "Final PnL": total_stock_pl,
        "Buy & Hold PnL": total_stock_pl,
        "Hedge PnL": 0,
        "Win Rate %": (df["stock_pnl"] > 0).mean() * 100,
        "Max Drawdown": max_drawdown,
        "Volatility": vol,
        "Risk-Adjusted": risk_adj
    }

# === Single strategy run ===
if st.sidebar.button("Run Backtest ✅"):
    payload = {
        "ticker": ticker,
        "shares": shares,
        "strategy": strategy
    }
    if otm_percent is not None:
        payload["otm_percent"] = otm_percent
    if spread_width_percent is not None:
        payload["spread_width_percent"] = spread_width_percent
    if upside_cap_percent is not None:
        payload["upside_cap_percent"] = upside_cap_percent
    if coverage_ratio is not None:
        payload["coverage_ratio"] = coverage_ratio

    with st.spinner("Running backtest..."):
        resp = requests.post(FASTAPI_URL, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if "results" in data:
                df = pd.DataFrame(data["results"])
                st.success(data["status"])

                # === Enhanced Summary ===
                if "summary" in data:
                    st.subheader("📊 Summary")
                    summary = data["summary"]

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Months Tested", summary.get("months", 0))
                        st.metric("Win Rate %", summary.get("win_rate_percent", 0))
                    with c2:
                        st.metric("Buy & Hold Stock PnL", f"${summary.get('total_stock_pl',0):,.0f}")
                        st.metric("Hedge Net PnL", f"${summary.get('total_hedge_pl',0):,.0f}")
                    with c3:
                        st.metric("Strategy Final PnL", f"${summary.get('total_strategy_pl',0):,.0f}")
                        st.metric("Hedge vs Stock %", f"{summary.get('hedge_pct_of_stock',0):,.1f}%")

                    # Risk metrics row
                    r1, r2 = st.columns(2)
                    with r1:
                        st.metric("Max Drawdown", f"${summary.get('max_drawdown',0):,.0f}")
                    with r2:
                        st.metric("Monthly Volatility", f"${summary.get('monthly_volatility',0):,.0f}")

                    # Quick comparison chart
                    st.subheader("Buy & Hold vs Strategy")
                    comp_df = pd.DataFrame({
                        "PnL": [
                            summary.get("total_stock_pl",0),
                            summary.get("total_strategy_pl",0)
                        ]
                    }, index=["Buy & Hold", "Strategy"])
                    st.bar_chart(comp_df)

                # === Detailed Table ===
                st.subheader("Detailed Monthly Results")
                st.dataframe(df, use_container_width=True)

                # === Plot cumulative strategy vs stock PnL ===
                if "total_pnl" in df.columns:
                    st.subheader("Cumulative Strategy vs Stock PnL")
                    cum_df = pd.DataFrame({
                        "Cumulative Strategy PnL": df["total_pnl"].cumsum(),
                        "Cumulative Stock PnL": df["stock_pnl"].cumsum()
                    })
                    st.line_chart(cum_df)

            else:
                st.error("No results returned!")
        else:
            st.error(f"Error {resp.status_code}: {resp.text}")
else:
    st.info("Choose your strategy and click **Run Backtest ✅**")

# === Multi-strategy comparison ===
ALL_STRATEGIES = [
    "rolling_atm_puts",
    "rolling_otm_puts",
    "rolling_put_spread",
    "rolling_collar",
    "rolling_zero_cost_collar"
]

if st.sidebar.button("Compare ALL Strategies 🚀"):
    comp_results = []
    with st.spinner("Running all strategies..."):
        # Run Buy & Hold baseline first
        bh_metrics = run_buy_and_hold(shares)
        if bh_metrics:
            comp_results.append(bh_metrics)

        # Then run all hedging strategies
        for strat in ALL_STRATEGIES:
            data = run_strategy(strat, shares)
            if data and "summary" in data:
                summary = data["summary"]
                comp_results.append({
                    "Strategy": strat,
                    "Final PnL": summary["total_strategy_pl"],
                    "Buy & Hold PnL": summary["total_stock_pl"],
                    "Hedge PnL": summary["total_hedge_pl"],
                    "Win Rate %": summary["win_rate_percent"],
                    "Max Drawdown": summary["max_drawdown"],
                    "Volatility": summary["monthly_volatility"],
                    "Risk-Adjusted": (
                        summary["avg_monthly_strategy_pl"] / summary["monthly_volatility"]
                        if summary["monthly_volatility"] > 0 else 0
                    )
                })

    if comp_results:
        df_comp = pd.DataFrame(comp_results)

        st.subheader("📊 Multi-Strategy Comparison")
        st.dataframe(df_comp.style.format({
            "Final PnL": "${:,.0f}",
            "Buy & Hold PnL": "${:,.0f}",
            "Hedge PnL": "${:,.0f}",
            "Max Drawdown": "${:,.0f}",
            "Volatility": "${:,.0f}",
            "Risk-Adjusted": "{:.2f}"
        }), use_container_width=True)

        # Sort by Risk-Adjusted Return
        best = df_comp.sort_values("Risk-Adjusted", ascending=False).iloc[0]
        st.success(f"🏆 Best Risk-Adjusted Strategy: **{best['Strategy']}**")

        # === Final PnL: one bar per strategy ===
        pnl_df = df_comp.copy()
        # For Buy & Hold row, Final PnL = Buy & Hold PnL
        pnl_df.loc[pnl_df["Strategy"] == "Buy & Hold", "Final PnL"] = pnl_df.loc[
            pnl_df["Strategy"] == "Buy & Hold", "Buy & Hold PnL"
        ]
        pnl_chart = alt.Chart(pnl_df).mark_bar().encode(
            x=alt.X('Strategy:N', sort=None, title="Strategy"),
            y=alt.Y('Final PnL:Q', title="Final PnL ($)"),
            color=alt.Color('Strategy:N', legend=None)
        )
        st.subheader("Final PnL Comparison")
        st.altair_chart(pnl_chart, use_container_width=True)

        # === Max Drawdown one bar per strategy ===
        dd_df = df_comp[["Strategy", "Max Drawdown"]]
        dd_chart = alt.Chart(dd_df).mark_bar().encode(
            x=alt.X('Strategy:N', sort=None, title="Strategy"),
            y=alt.Y('Max Drawdown:Q', title="Max Drawdown ($)"),
            color=alt.Color('Strategy:N', legend=None)
        )
        st.subheader("Max Drawdown Comparison")
        st.altair_chart(dd_chart, use_container_width=True)

        # === Volatility one bar per strategy ===
        vol_df = df_comp[["Strategy", "Volatility"]]
        vol_chart = alt.Chart(vol_df).mark_bar().encode(
            x=alt.X('Strategy:N', sort=None, title="Strategy"),
            y=alt.Y('Volatility:Q', title="Monthly Volatility ($)"),
            color=alt.Color('Strategy:N', legend=None)
        )
        st.subheader("Volatility Comparison")
        st.altair_chart(vol_chart, use_container_width=True)

    else:
        st.error("No strategy results returned.")
