"""F&O Agent Studio - Streamlit version (reuses agent.py). Deploy free on Streamlit Community Cloud."""
import os

os.environ.setdefault("DISABLE_LLM", "1")  # no Ollama on the cloud; set DISABLE_LLM=0 locally to use it

import altair as alt
import pandas as pd
import streamlit as st

import agent

st.set_page_config(page_title="F&O Agent Studio", page_icon="🌿", layout="wide")
st.markdown("""
<style>
  .block-container{padding-top:1.2rem}
  .hero{background:#5F7355;color:#fff;padding:18px 24px;border-radius:14px;margin-bottom:14px}
  .hero h1{margin:0;font-size:1.5rem;color:#fff}.hero span{opacity:.85;font-size:.9rem}
  .stButton>button{background:#5F7355;color:#fff;border:0;border-radius:8px}
  .stButton>button:hover{background:#3F4F38;color:#fff}
  .ans{background:#E6EDDF;border-radius:10px;padding:14px;line-height:1.55;white-space:pre-wrap}
</style>
<div class="hero"><h1>F&amp;O Agent Studio</h1>
<span>Multi-agent learning assistant for futures &amp; options. Educational only, not investment advice.</span></div>
""", unsafe_allow_html=True)


def trace_panel(trace):
    with st.sidebar:
        st.subheader("Agent trace")
        for t in trace:
            st.markdown("**%s**  \n%s" % (t["agent"], t["action"]))


with st.sidebar:
    st.caption("Agents: Router, Concept, Pricing, Strategy, Risk Guard, Compliance Guard")

tab_ask, tab_price, tab_strat = st.tabs(["Ask the Agent", "Option Pricer", "Strategy Lab"])

with tab_ask:
    examples = ["What is delta?", "Explain iron condor", "How does margin work?", "What is PCR?"]
    cols = st.columns(len(examples))
    for c, e in zip(cols, examples):
        if c.button(e, width="stretch"):
            st.session_state["q"] = e
    q = st.text_area("Ask about F&O concepts", key="q", placeholder="e.g. What is theta decay and why do sellers like it?")
    if st.button("Ask") and q.strip():
        res = agent.ask(q.strip()[:500])
        st.markdown('<div class="ans">%s</div>' % res["answer"].replace("<", "&lt;"), unsafe_allow_html=True)
        st.caption(("Sources: " + ", ".join(res["sources"]) + " · " if res["sources"] else "") + "%d ms" % res["latency_ms"])
        trace_panel(res["trace"])

with tab_price:
    c1, c2, c3 = st.columns(3)
    spot = c1.number_input("Spot", value=24000.0, min_value=1.0)
    strike = c2.number_input("Strike", value=24200.0, min_value=1.0)
    days = c3.number_input("Days to expiry", value=7, min_value=1)
    c4, c5, c6 = st.columns(3)
    vol = c4.number_input("IV (%)", value=14.0, min_value=0.1)
    rate = c5.number_input("Risk-free rate (%)", value=6.5)
    kind = c6.selectbox("Type", ["CE", "PE"], format_func=lambda k: "Call (CE)" if k == "CE" else "Put (PE)")
    if st.button("Calculate"):
        r = agent.black_scholes(spot, strike, days, rate, vol, kind)
        m = st.columns(3)
        m[0].metric("Theoretical price", r["price"])
        m[1].metric("Intrinsic", r["intrinsic"])
        m[2].metric("Time value", r["time_value"])
        g = st.columns(4)
        g[0].metric("Delta", r["delta"]); g[1].metric("Gamma", r["gamma"])
        g[2].metric("Theta/day", r["theta_per_day"]); g[3].metric("Vega/1% IV", r["vega_per_1pct"])
        trace_panel([{"agent": "Router", "action": "route to Pricing Agent"},
                     {"agent": "Pricing Agent", "action": "Black-Scholes price and Greeks"}])

with tab_strat:
    c1, c2, c3, c4 = st.columns(4)
    preset = c1.selectbox("Strategy", list(agent.PRESETS), format_func=lambda s: s.replace("_", " ").title())
    s_spot = c2.number_input("Spot ", value=24000.0, min_value=1.0)
    step = c3.number_input("Strike step", value=50.0, min_value=1.0)
    lot = c4.number_input("Lot size (check NSE)", value=75, min_value=1)
    if st.button("Build payoff"):
        legs = agent.PRESETS[preset](s_spot, step, float(lot))
        p = agent.payoff(legs, s_spot)
        warns = agent.risk_guard(legs)
        fmt = lambda v: "Unlimited" if v is None else "₹{:,.0f}".format(v)
        m = st.columns(3)
        m[0].metric("Max profit", "Unlimited" if p["max_profit_unlimited"] else fmt(p["max_profit"]))
        m[1].metric("Max loss", "Unlimited" if p["max_loss_unlimited"] else fmt(p["max_loss"]))
        m[2].metric("Breakevens", " / ".join(str(b) for b in p["breakevens"]) or "-")
        for w in warns:
            st.warning(w)
        df = pd.DataFrame(p["points"], columns=["Underlying at expiry", "Profit / Loss (₹)"])
        chart = alt.Chart(df).mark_area(line={"color": "#5F7355"}, color="#9CAF88", opacity=0.4).encode(
            x="Underlying at expiry:Q", y="Profit / Loss (₹):Q")
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#6B7861").encode(y="y:Q")
        st.altair_chart(chart + zero, width="stretch")
        st.dataframe(pd.DataFrame(legs), width="stretch", hide_index=True)
        trace_panel([{"agent": "Router", "action": "route to Strategy Agent"},
                     {"agent": "Strategy Agent", "action": "compute expiry payoff and breakevens"},
                     {"agent": "Risk Guard", "action": "%d warning(s)" % len(warns)}])
    st.caption("Premiums are illustrative Black-Scholes values (14% IV, 7 days), not live market data.")
