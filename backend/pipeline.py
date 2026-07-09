"""Batch runner over all 100 apps. Checkpointed: every finished app is
appended to checkpoints.jsonl immediately, so a crash/rate-limit death loses
at most the apps in flight — rerunning resumes, never restarts.

Usage:
    python -m backend.pipeline                # run / resume the batch
    python -m backend.pipeline --retry-errors # also redo rows that errored
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .agent import research_app
from .schemas import AppInput, AppResearch

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
APPS_FILE = DATA_DIR / "apps.json"
CHECKPOINTS_FILE = DATA_DIR / "checkpoints.jsonl"
RESULTS_FILE = DATA_DIR / "results.json"

# App-level parallelism. LLM calls are further capped by llm.py's semaphore,
# so this mostly parallelises the docs fetching, which is the slow part.
CONCURRENCY = 8


def load_apps() -> list[AppInput]:
    return [AppInput(**a) for a in json.loads(APPS_FILE.read_text())]


def load_checkpoints() -> dict[str, AppResearch]:
    """Read finished rows keyed by app id. Later lines win (reruns)."""
    done: dict[str, AppResearch] = {}
    if CHECKPOINTS_FILE.exists():
        for line in CHECKPOINTS_FILE.read_text().splitlines():
            if line.strip():
                row = AppResearch.model_validate_json(line)
                done[row.id] = row
    return done


def assemble_results(done: dict[str, AppResearch]) -> None:
    """Write results.json in apps.json order — the file /data.json serves."""
    rows = [done[a.id].model_dump(mode="json")
            for a in load_apps() if a.id in done]
    RESULTS_FILE.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(rows),
        "apps": rows,
    }, indent=2))
    print(f"\nwrote {RESULTS_FILE.name} with {len(rows)} apps")


async def run_batch(retry_errors: bool = False) -> None:
    apps = load_apps()
    done = load_checkpoints()
    if retry_errors:  # drop failed rows from 'done' so they get redone
        done = {i: r for i, r in done.items() if r.error is None}

    todo = [a for a in apps if a.id not in done]
    print(f"{len(done)} checkpointed, {len(todo)} to research")

    sem = asyncio.Semaphore(CONCURRENCY)
    write_lock = asyncio.Lock()  # jsonl appends must not interleave
    finished = 0

    async def worker(app: AppInput) -> None:
        nonlocal finished
        async with sem:
            row = await research_app(app)
        async with write_lock:
            with CHECKPOINTS_FILE.open("a") as f:
                f.write(row.model_dump_json() + "\n")
        done[app.id] = row
        finished += 1
        verdict = row.result.buildability.value if row.result \
            else f"ERROR: {row.error}"
        print(f"[{finished}/{len(todo)}] {app.name}: {verdict}")

    await asyncio.gather(*(worker(a) for a in todo))
    assemble_results(done)


if __name__ == "__main__":
    asyncio.run(run_batch(retry_errors="--retry-errors" in sys.argv))
