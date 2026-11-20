"""F&O Agent Studio - Flask server. Run locally: python app.py  (opens in Brave/Chrome/Safari)."""
import json
import os
import platform
import subprocess
import threading
import time
import webbrowser

from flask import Flask, jsonify, request, send_from_directory

import agent

app = Flask(__name__, static_folder="static")
PORT = int(os.environ.get("PORT", 5055))
API_KEY = os.environ.get("APP_API_KEY")  # optional: set on cloud to require X-API-Key
LOG = os.path.join(os.path.dirname(__file__), "audit.jsonl")


def audit(event, data):
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps({"ts": time.time(), "event": event, **data}) + "\n")
    except OSError:
        pass  # read-only filesystem on some free hosts


@app.before_request
def guard():
    if API_KEY and request.path.startswith("/api/") and request.headers.get("X-API-Key") != API_KEY:
        return jsonify(error="unauthorized"), 401


@app.get("/")
def home():
    return send_from_directory("static", "index.html")


@app.get("/health")
def health():
    return jsonify(status="ok", service="fno-agent-studio")


@app.post("/api/ask")
def api_ask():
    q = (request.json or {}).get("question", "").strip()
    if not q:
        return jsonify(error="question required"), 400
    res = agent.ask(q[:500])
    audit("ask", {"q": q[:200], "route": res["route"], "ms": res["latency_ms"]})
    return jsonify(res)


@app.post("/api/price")
def api_price():
    d = request.json or {}
    try:
        out = agent.black_scholes(d["spot"], d["strike"], d["days"], d.get("rate", 6.5), d["vol"], d.get("type", "CE"))
    except (KeyError, ValueError, ZeroDivisionError) as e:
        return jsonify(error=str(e)), 400
    audit("price", {"input": d})
    return jsonify(result=out, trace=[{"agent": "Router", "action": "route to Pricing Agent"},
                                      {"agent": "Pricing Agent", "action": "Black-Scholes price and Greeks"}])


@app.post("/api/strategy")
def api_strategy():
    d = request.json or {}
    try:
        spot = float(d["spot"])
        legs = d.get("legs")
        if not legs:
            step, lot = float(d.get("step", 50)), float(d.get("lot", 75))
            legs = agent.PRESETS[d["preset"]](spot, step, lot)
        result = agent.payoff(legs, spot)
        warnings = agent.risk_guard(legs)
    except (KeyError, ValueError, TypeError) as e:
        return jsonify(error="invalid input: %s" % e), 400
    audit("strategy", {"preset": d.get("preset"), "warnings": len(warnings)})
    trace = [{"agent": "Router", "action": "route to Strategy Agent"},
             {"agent": "Strategy Agent", "action": "compute expiry payoff and breakevens"},
             {"agent": "Risk Guard", "action": "%d warning(s)" % len(warnings)}]
    return jsonify(legs=legs, payoff=result, warnings=warnings, trace=trace)


def open_browser(url):
    """Open in an external browser: Brave first on macOS, then Chrome, Safari, then system default."""
    if platform.system() == "Darwin":
        for name in ("Brave Browser", "Google Chrome", "Safari"):
            if subprocess.run(["open", "-a", name, url], capture_output=True).returncode == 0:
                return
    webbrowser.open(url)


if __name__ == "__main__":
    url = "http://127.0.0.1:%d" % PORT
    on_cloud = bool(os.environ.get("RENDER") or os.environ.get("SPACE_ID") or os.environ.get("K_SERVICE"))
    if not on_cloud:
        threading.Timer(1.0, open_browser, args=(url,)).start()
    print("F&O Agent Studio running at", url)
    app.run(host="0.0.0.0" if on_cloud else "127.0.0.1", port=PORT, debug=False)
