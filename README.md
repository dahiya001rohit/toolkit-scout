# toolkit-scout

An agent that researched **100 apps** — auth methods, API surface, self-serve vs
gated credentials, MCP availability — and judged whether each could become an
AI-agent toolkit today. Built for Composio's AI Product Ops take-home.

**Live case study:** _link added at deploy_ · **Raw data:** `/data.json` on the backend

## How it works

```
data/apps.json ──► pipeline.py ──► agent.py (per app) ──► checkpoints.jsonl ──► results.json
                                    │ 1. URL discovery (hint → docs.X guesses →
                                    │    links mined from pages → LLM URL suggestions)
                                    │ 2. httpx fetch, up to 3 real docs pages
                                    │ 3. Groq extraction, pydantic-enforced schema,
                                    │    grounded ONLY in fetched text
                                    ▼
                   verify.py ──► verification.json  (pass 2: re-fetch, skeptical
                                 re-extract on a different model, field diff,
                                 quote-backed tie-breaks, corrections applied)
```

Key properties:

- **No answers from LLM memory.** Every claim is extracted from fetched page text
  and carries the docs URL behind it. "Couldn't find it" is a legal, honest answer.
- **Checkpointed.** Every finished app is written to `data/checkpoints.jsonl`
  immediately; reruns resume instead of restarting.
- **Quota-aware model pool.** Groq free-tier limits are per model — on a daily-quota
  429 the agent rotates to the next model instead of dying.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp .env.example .env        # add your GROQ_API_KEY (free: console.groq.com/keys)

# research all 100 apps (resumable; rerun with --retry-errors to redo failures)
.venv/bin/python -m backend.pipeline

# pass-2 verification (diffs, tie-breaks, corrections, accuracy stats)
.venv/bin/python -m backend.verify

# serve the API (data.json, verification.json, live /research SSE demo)
.venv/bin/uvicorn backend.main:app --port 8000

# frontend (static; expects backend on localhost:8000 unless window.TS_API is set)
cd frontend && python3 -m http.server 8080
```

## Repo map

| Path | What it is |
|---|---|
| `backend/schemas.py` | pydantic contract: enums + models every LLM output must satisfy |
| `backend/llm.py` | Groq wrapper: JSON-mode extraction, validation retries, model pool |
| `backend/agent.py` | single-app researcher: discover → fetch → grounded extract |
| `backend/pipeline.py` | 100-app batch runner, checkpointed + resumable |
| `backend/verify.py` | verification pass: cross-model re-extract, diff, tie-break |
| `backend/main.py` | FastAPI: SSE live demo, data endpoints, health + keep-alive |
| `frontend/` | the case-study page (vanilla HTML/CSS/JS, no build step) |
| `data/` | input list, checkpoints, final results, verification report |

## Honesty notes

- PitchBook could not be fetched at all (bot-blocked, partnership-gated API) — it is
  reported as an evidenced failure, not guessed around.
- Pass 1 ran on two models (llama-3.3-70b for the first 27 apps, gpt-oss-120b after a
  daily-quota rotation). Disclosed because it makes rows slightly inconsistent — and
  exploited: verification deliberately re-checks cross-model.
- Fetched text is truncated (~4k chars/page), so API-breadth judgments lean on docs
  landing pages more than exhaustive endpoint references.
