"""FastAPI app — the live layer over the research pipeline.

Endpoints:
  GET /health             liveness probe (also the keep-alive target)
  GET /data.json          final research results (agent-consumable)
  GET /verification.json  pass-2 verification report
  GET /research?name=X    live single-app research, streamed as SSE

Keep-alive: Render's free tier idles the server after ~15 min without
traffic. On startup we self-ping /health every 8 minutes via the public
URL (Render injects RENDER_EXTERNAL_URL) so reviewers never hit a cold start.
"""

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from .agent import research_app
from .pipeline import DATA_DIR
from .schemas import AppInput

KEEP_ALIVE_SECS = 8 * 60          # under Render's ~15 min idle window
DEMO_LIMIT_PER_HOUR = 6           # per-IP budget for live researches
_demo_sem = asyncio.Semaphore(2)  # global cap: protect the LLM quota
_hits: dict[str, list[float]] = {}


async def _keep_alive() -> None:
    """Self-ping the public /health URL forever (no-op when not deployed)."""
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        return
    async with httpx.AsyncClient() as client:
        while True:
            await asyncio.sleep(KEEP_ALIVE_SECS)
            try:
                await client.get(f"{url}/health", timeout=10)
            except httpx.HTTPError:
                pass              # a missed ping is not worth crashing over


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_keep_alive())
    yield
    task.cancel()


app = FastAPI(title="toolkit-scout", lifespan=lifespan)

# Frontend is served from a different origin (Vercel) — allow it to call us.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "time": time.time()}


@app.get("/")
async def root() -> dict:
    return {"service": "toolkit-scout",
            "endpoints": ["/health", "/data.json", "/verification.json",
                          "/research?name=<app>&hint=<url>"]}


@app.get("/data.json")
async def data():
    path = DATA_DIR / "results.json"
    if not path.exists():
        return JSONResponse({"error": "no results yet"}, status_code=404)
    return FileResponse(path, media_type="application/json")


@app.get("/verification.json")
async def verification():
    path = DATA_DIR / "verification.json"
    if not path.exists():
        return JSONResponse({"error": "no verification yet"}, status_code=404)
    return FileResponse(path, media_type="application/json")


def _rate_ok(ip: str) -> bool:
    """Sliding-window limiter: DEMO_LIMIT_PER_HOUR researches per IP."""
    now = time.time()
    window = [t for t in _hits.get(ip, []) if now - t < 3600]
    if len(window) >= DEMO_LIMIT_PER_HOUR:
        _hits[ip] = window
        return False
    _hits[ip] = window + [now]
    return True


@app.get("/research")
async def research(request: Request, name: str, hint: str = ""):
    """Research ANY app live; progress + result streamed as SSE events.

    Same single-pass path as the batch (fetch -> grounded extract), no
    verification pass — deliberately the cheap route for public traffic.
    """
    name = name.strip()[:80]
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=422)
    ip = request.client.host if request.client else "?"
    if not _rate_ok(ip):
        return JSONResponse(
            {"error": f"rate limit: {DEMO_LIMIT_PER_HOUR} researches/hour"},
            status_code=429)

    # Hint fallback: crude domain guess; agent's URL discovery + LLM guess
    # step handle the misses, and a wrong guess just 404s.
    app_input = AppInput(
        id=uuid.uuid4().hex[:6], name=name, category="live-demo",
        hint=hint.strip() or name.lower().replace(" ", "") + ".com")

    async def gen():
        q: asyncio.Queue = asyncio.Queue()

        async def progress(msg: str) -> None:
            await q.put(("step", msg))

        async def run() -> None:
            try:
                async with _demo_sem:
                    row = await research_app(app_input, progress)
                await q.put(("result", row.model_dump_json()))
            except Exception as e:      # graceful failure, never a raw 500
                await q.put(("error", f"research failed: {e}"))
            await q.put(("done", ""))

        task = asyncio.create_task(run())
        try:
            while True:
                event, payload = await q.get()
                if event == "done":
                    break
                yield {"event": event, "data": payload}
        finally:
            task.cancel()               # client disconnected mid-stream

    return EventSourceResponse(gen())
