#!/bin/bash
# One-command local start on macOS: creates venv, installs deps, launches app (opens Brave).
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python app.py
