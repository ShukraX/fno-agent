#!/bin/bash
# Local Streamlit start on macOS; opens Brave (falls back to Chrome, Safari).
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
URL="http://localhost:8501"
( sleep 3; open -a "Brave Browser" "$URL" || open -a "Google Chrome" "$URL" || open "$URL" ) &
DISABLE_LLM=0 streamlit run streamlit_app.py --server.headless true --server.port 8501
