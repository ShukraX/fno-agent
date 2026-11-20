"""F&O multi-agent core: router, concept agent (RAG), pricing agent, strategy agent, risk guard.
Pure Python standard library + requests. Educational use only - not investment advice."""
import math
import os
import re
import time

import requests

# ---------------------------------------------------------------- knowledge base
KB = [
    ("Futures contract", "futures forward contract lot expiry margin",
     "A futures contract is an agreement to buy or sell an underlying (index or stock) at a fixed price on a fixed expiry date. "
     "It trades in lots, needs only margin (not full value) and is marked to market daily, so profits and losses are settled every day."),
    ("Call and put options", "call put option premium strike buyer seller writer",
     "A call gives the buyer the right (not obligation) to buy the underlying at the strike; a put gives the right to sell. "
     "The buyer pays a premium and risk is limited to it. The seller (writer) receives the premium but carries large risk and must post margin."),
    ("Moneyness: ITM, ATM, OTM", "itm atm otm moneyness intrinsic extrinsic time value",
     "A call is ITM when spot > strike, a put is ITM when spot < strike. ATM means spot is near strike. OTM options have only time value. "
     "Premium = intrinsic value + time (extrinsic) value; time value decays as expiry nears."),
    ("Lot size and expiry", "lot size expiry weekly monthly contract multiplier",
     "F&O contracts trade in fixed lots (quantity per lot). Lot sizes and expiry days are set by the exchange and are revised from time to time, "
     "so always confirm the current values on the NSE website before computing exposure."),
    ("Margin (SPAN + Exposure)", "margin span exposure mtm blocked capital leverage",
     "Margin is the collateral blocked to hold a position. It is commonly SPAN margin (worst-case loss estimate) plus exposure margin. "
     "Option buyers pay only the premium; option sellers and futures traders must block margin and can face margin calls when prices move against them."),
    ("Delta", "delta greeks direction hedge ratio",
     "Delta measures how much an option price changes for a 1-point move in the underlying. Calls have delta 0 to +1, puts 0 to -1. "
     "ATM options are near 0.5 in absolute terms. Delta is also a rough probability of finishing ITM."),
    ("Gamma", "gamma convexity greeks acceleration",
     "Gamma is the rate of change of delta. It is highest for ATM options close to expiry, which is why short-dated ATM options move fast and are risky to sell."),
    ("Theta", "theta time decay greeks",
     "Theta is the daily loss of option value from time passing. Buyers fight theta; sellers earn it. Decay accelerates in the last days before expiry for ATM options."),
    ("Vega and implied volatility", "vega iv implied volatility greeks vix",
     "Vega is the change in option price for a 1 percentage-point change in implied volatility (IV). IV is the market's expected future movement backed out of the price. "
     "High IV makes options expensive; an IV crush after events (results, budget) can hurt option buyers even if direction is right."),
    ("Open interest and PCR", "open interest oi pcr put call ratio volume",
     "Open interest (OI) is the number of outstanding contracts. Rising price with rising OI suggests fresh long positions; falling price with rising OI suggests fresh shorts. "
     "Put-Call Ratio (PCR) = put OI / call OI and is used as a sentiment gauge."),
    ("Long straddle / strangle", "straddle strangle volatility breakout long short",
     "A long straddle buys a call and put at the same strike; a strangle uses different strikes. Both profit from a large move in either direction and lose if the market stays flat. "
     "Selling them earns premium in range-bound markets but has very large risk."),
    ("Bull call spread / bear put spread", "bull call spread bear put spread debit vertical limited risk",
     "A bull call spread buys a lower-strike call and sells a higher-strike call: cheaper than a naked call, with capped profit and capped loss. "
     "A bear put spread is the bearish mirror using puts."),
    ("Iron condor", "iron condor range bound neutral credit",
     "An iron condor sells an OTM call spread and an OTM put spread. It earns a net credit if the underlying stays between the short strikes, with defined maximum loss."),
    ("Covered call and protective put", "covered call protective put hedge hedging collar",
     "A covered call holds the underlying and sells a call to earn income. A protective put holds the underlying and buys a put as insurance. Both are hedging building blocks."),
    ("Rollover", "rollover roll expiry carry next month",
     "Rollover means closing the near-month position and opening the same position in the next expiry to keep exposure without taking delivery or settlement."),
    ("Max pain", "max pain expiry pinning option writers",
     "Max pain is the strike at which option buyers collectively lose the most (writers gain the most) at expiry. Some traders watch it for pinning behaviour; it is not a reliable predictor."),
    ("Risk management basics", "risk stop loss position sizing capital drawdown naked",
     "Size positions so a single loss is a small fraction of capital, prefer defined-risk strategies (spreads) while learning, avoid naked option selling without margin buffer, "
     "and track total delta, theta and vega of the portfolio."),
]

STOP = set("the a an is are of to in on for and or what how why does do i me my it with as at by be can".split())


def _tok(text):
    return [w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP]


def retrieve(query, k=2):
    q = set(_tok(query))
    scored = []
    for title, kw, text in KB:
        words = set(_tok(title + " " + kw))
        body = set(_tok(text))
        score = 3 * len(q & words) + len(q & body)
        if score:
            scored.append((score, title, text))
    scored.sort(reverse=True)
    return [{"title": t, "text": x, "score": s} for s, t, x in scored[:k]]


# ---------------------------------------------------------------- pricing tools
def _cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def black_scholes(spot, strike, days, rate_pct, vol_pct, kind):
    S, K = float(spot), float(strike)
    T = max(float(days), 0.0001) / 365.0
    r, v = float(rate_pct) / 100, max(float(vol_pct) / 100, 1e-6)
    if S <= 0 or K <= 0:
        raise ValueError("spot and strike must be positive")
    d1 = (math.log(S / K) + (r + v * v / 2) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    disc = math.exp(-r * T)
    if kind == "CE":
        price = S * _cdf(d1) - K * disc * _cdf(d2)
        delta = _cdf(d1)
        theta = (-S * _pdf(d1) * v / (2 * math.sqrt(T)) - r * K * disc * _cdf(d2)) / 365
    else:
        price = K * disc * _cdf(-d2) - S * _cdf(-d1)
        delta = _cdf(d1) - 1
        theta = (-S * _pdf(d1) * v / (2 * math.sqrt(T)) + r * K * disc * _cdf(-d2)) / 365
    gamma = _pdf(d1) / (S * v * math.sqrt(T))
    vega = S * _pdf(d1) * math.sqrt(T) / 100
    intrinsic = max(S - K, 0) if kind == "CE" else max(K - S, 0)
    return {"price": round(price, 2), "delta": round(delta, 4), "gamma": round(gamma, 6),
            "theta_per_day": round(theta, 2), "vega_per_1pct": round(vega, 2),
            "intrinsic": round(intrinsic, 2), "time_value": round(price - intrinsic, 2)}


def payoff(legs, spot):
    """legs: [{type: CE|PE|FUT, side: buy|sell, strike, premium, qty}] -> payoff at expiry."""
    spot = float(spot)
    lo, hi = spot * 0.7, spot * 1.3
    xs = [lo + (hi - lo) * i / 160 for i in range(161)]
    for l in legs:
        xs.append(float(l["strike"]))
    xs = sorted(set(xs))
    pts = []
    for s in xs:
        total = 0.0
        for l in legs:
            K, prem, q = float(l["strike"]), float(l.get("premium", 0)), float(l["qty"])
            sign = 1 if l["side"] == "buy" else -1
            if l["type"] == "CE":
                v = max(s - K, 0) - prem
            elif l["type"] == "PE":
                v = max(K - s, 0) - prem
            else:
                v = s - K
            total += sign * v * q
        pts.append((round(s, 2), round(total, 2)))
    ys = [p[1] for p in pts]
    bes = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if y1 == 0:
            bes.append(x1)
        elif y1 * y2 < 0:
            bes.append(round(x1 + (x2 - x1) * (-y1) / (y2 - y1), 2))
    unbounded_up = pts[-1][1] > pts[-2][1] and pts[-1][1] > 0
    unbounded_down_right = pts[-1][1] < pts[-2][1] and pts[-1][1] < 0
    return {"points": pts, "max_profit": None if unbounded_up else max(ys),
            "max_loss": None if unbounded_down_right else min(ys),
            "max_profit_unlimited": unbounded_up, "max_loss_unlimited": unbounded_down_right,
            "breakevens": sorted(set(bes))}


def risk_guard(legs):
    """Flags naked short exposure. Returns list of warnings."""
    warns = []
    short_ce = sum(float(l["qty"]) for l in legs if l["type"] == "CE" and l["side"] == "sell")
    long_ce = sum(float(l["qty"]) for l in legs if l["type"] == "CE" and l["side"] == "buy")
    long_fut = sum(float(l["qty"]) for l in legs if l["type"] == "FUT" and l["side"] == "buy")
    short_pe = sum(float(l["qty"]) for l in legs if l["type"] == "PE" and l["side"] == "sell")
    long_pe = sum(float(l["qty"]) for l in legs if l["type"] == "PE" and l["side"] == "buy")
    if short_ce > long_ce + long_fut:
        warns.append("Naked short call: loss is theoretically unlimited. Needs large margin; consider buying a higher-strike call to cap risk.")
    if short_pe > long_pe:
        warns.append("Short put without a hedge: loss can be very large if the market falls sharply. Consider a bought lower-strike put.")
    if any(l["type"] == "FUT" and l["side"] == "sell" for l in legs):
        warns.append("Short futures carry unlimited upside risk and daily mark-to-market margin calls.")
    return warns


def _leg(kind, side, strike, spot, lot, days=7, vol=14.0):
    """Leg with an illustrative premium from Black-Scholes (not live market data)."""
    prem = black_scholes(spot, strike, days, 6.5, vol, kind)["price"]
    return {"type": kind, "side": side, "strike": strike, "premium": prem, "qty": lot}


PRESETS = {
    "long_straddle": lambda spot, step, lot: [
        _leg("CE", "buy", spot, spot, lot), _leg("PE", "buy", spot, spot, lot)],
    "bull_call_spread": lambda spot, step, lot: [
        _leg("CE", "buy", spot, spot, lot), _leg("CE", "sell", spot + 4 * step, spot, lot)],
    "iron_condor": lambda spot, step, lot: [
        _leg("PE", "buy", spot - 8 * step, spot, lot), _leg("PE", "sell", spot - 4 * step, spot, lot),
        _leg("CE", "sell", spot + 4 * step, spot, lot), _leg("CE", "buy", spot + 8 * step, spot, lot)],
    "naked_short_call": lambda spot, step, lot: [
        _leg("CE", "sell", spot + 2 * step, spot, lot)],
}


# ---------------------------------------------------------------- LLM (optional)
def _llm(question, context):
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    if os.environ.get("DISABLE_LLM") == "1":
        return None
    prompt = ("You are an F&O (futures and options) tutor for Indian markets. Answer in under 150 words using ONLY the context. "
              "Educational only; never give buy/sell tips.\n\nContext:\n" + context + "\n\nQuestion: " + question)
    try:
        r = requests.post(url + "/api/generate", json={"model": model, "prompt": prompt, "stream": False}, timeout=60)
        if r.ok:
            return r.json().get("response", "").strip() or None
    except requests.RequestException:
        return None
    return None


# ---------------------------------------------------------------- agents + router
TIPS_RE = re.compile(r"\b(should i (buy|sell)|which stock|guaranteed|sure shot|tip|target price)\b", re.I)


def router(question):
    q = question.lower()
    if TIPS_RE.search(q):
        return "guard"
    if re.search(r"\b(price|premium|black.?scholes|greeks?)\b.*\d", q):
        return "pricing"
    return "concept"


def ask(question):
    t0 = time.time()
    trace = [{"agent": "Router", "action": "classify intent"}]
    route = router(question)
    if route == "guard":
        trace.append({"agent": "Compliance Guard", "action": "blocked trade-tip request"})
        answer = ("I can't give buy/sell tips or price targets. I can explain how a strategy works, what it costs, "
                  "and what the risks are, so you can decide with your own research or a SEBI-registered advisor.")
        sources = []
    else:
        trace.append({"agent": "Concept Agent", "action": "retrieve from F&O knowledge base"})
        docs = retrieve(question)
        sources = [d["title"] for d in docs]
        if not docs:
            answer = "I don't have that in my F&O knowledge base yet. Try asking about futures, options, Greeks, margin, OI/PCR or strategies like straddles and spreads."
        else:
            ctx = "\n\n".join(d["title"] + ": " + d["text"] for d in docs)
            llm = _llm(question, ctx)
            if llm:
                trace.append({"agent": "LLM (Ollama)", "action": "compose grounded answer"})
                answer = llm
            else:
                trace.append({"agent": "Concept Agent", "action": "LLM offline, returning knowledge-base text"})
                answer = "\n\n".join(d["title"] + " - " + d["text"] for d in docs)
    return {"answer": answer, "sources": sources, "trace": trace, "route": route,
            "latency_ms": int((time.time() - t0) * 1000)}
