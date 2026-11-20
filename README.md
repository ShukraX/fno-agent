# F&O Agent Studio

Multi-agent learning assistant for futures & options (Router, Concept Agent with retrieval, Pricing Agent with Black-Scholes Greeks, Strategy Agent with payoff charts, Risk Guard, Compliance Guard). Sage green and white UI. Educational only.

## Run locally (MacBook + VS Code, all free)
1. Open this folder in VS Code, then open the terminal (Ctrl+`).
2. `chmod +x run.sh && ./run.sh`
3. The app opens automatically in Brave (falls back to Chrome, Safari, then default browser) at http://127.0.0.1:5055

Optional local LLM: install Ollama (free), run `ollama pull llama3.2`. The Concept Agent will use it automatically. Without it, answers come straight from the built-in knowledge base.

## Deploy free on the cloud (Render)
1. Push this folder to a GitHub repo.
2. On render.com: New > Blueprint (or Web Service) > select the repo. It reads `render.yaml` and the Dockerfile; plan is Free.
3. Open the URL Render gives you. Cloud mode disables the local LLM and the auto-browser launch.
4. Optional security: add env var `APP_API_KEY` (the UI would then need to send X-API-Key; leave unset for a public demo).

Free instances sleep when idle, so the first request after a pause can take about a minute.

## Enterprise features included
Agent trace panel, audit log (audit.jsonl), /health endpoint, optional API-key auth, containerised deploy, guardrails (no trade tips, naked-short warnings).
# fno-agent
