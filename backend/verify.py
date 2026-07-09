"""Pass-2 verification. For every researched app: re-fetch its evidence
pages, re-extract with a skeptical-auditor prompt (different model where
possible), diff the error-prone fields, and let a third LLM call resolve
disagreements by quoting the evidence. Outputs:
  - data/verification.json   (diffs + agreement stats -> the honesty section)
  - data/results.json        (rewritten with corrections applied)

Usage:  python -m backend.verify        # checkpointed + resumable
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel

from .agent import _fetch, _html_to_text
from .llm import LLMError, extract
from .pipeline import DATA_DIR, assemble_results, load_checkpoints
from .schemas import AppResearch, ExtractionResult

VERIFY_CKPT = DATA_DIR / "verify_checkpoints.jsonl"
VERIFICATION_FILE = DATA_DIR / "verification.json"

# Only fields that are judgment-prone AND cluster the frontend. Description
# wording etc. differing between passes is not a disagreement.
FIELDS = ["auth_methods", "access", "api_type", "buildability", "has_mcp"]

# Pass 1 ran mostly on gpt-oss-120b (and llama for the first 27); preferring
# llama here makes most verifications cross-model. Pool rotates if exhausted.
VERIFY_MODEL = "llama-3.3-70b-versatile"

AUDIT_SYSTEM = (
    "You are a skeptical auditor double-checking API research. Extract "
    "answers using ONLY the provided page text. If the text does not state "
    "an answer, use 'unknown'/null — never guess from memory. Be strict: "
    "only claim an auth method, access level or MCP server if the text "
    "supports it."
)

TIEBREAK_SYSTEM = (
    "Two analysts disagree about fields extracted from the same pages. For "
    "each disputed field, pick the winner using ONLY the page text, and "
    "quote the exact sentence that decides it. If the text supports neither "
    "side, pick the more conservative answer (unknown/narrower claim)."
)


class FieldDiff(BaseModel):
    field: str
    pass1: str                    # values JSON-encoded for uniform diffing
    pass2: str
    agreed: bool
    final: str
    resolution: Literal["agreed", "kept_pass1", "corrected_to_pass2"]
    quote: str | None = None      # tie-break's evidence quote


class AppVerification(BaseModel):
    id: str
    name: str
    skipped: str | None = None    # e.g. no result / pages gone
    diffs: list[FieldDiff] = []


class _Resolution(BaseModel):
    field: str
    winner: Literal["pass1", "pass2"]
    quote: str


class _Resolutions(BaseModel):
    resolutions: list[_Resolution]


def _enc(result: ExtractionResult, field: str) -> str:
    val = result.model_dump(mode="json")[field]
    if isinstance(val, list):
        val = sorted(val)         # auth_methods order is not a disagreement
    return json.dumps(val)


async def _refetch(urls: list[str]) -> str:
    async with httpx.AsyncClient() as client:
        hits = await asyncio.gather(*(_fetch(client, u) for u in urls))
    return "\n\n".join(f"SOURCE: {u}\n{_html_to_text(html)}"
                       for hit in hits if hit for u, html in [hit])


async def verify_app(row: AppResearch) -> AppVerification:
    """Diff pass-1 vs a fresh skeptical extraction; tie-break disagreements."""
    out = AppVerification(id=row.id, name=row.name)
    if row.result is None:
        out.skipped = "no pass-1 result to verify"
        return out
    blocks = await _refetch(row.sources_fetched)
    if not blocks:
        out.skipped = "evidence pages no longer fetchable"
        return out

    user = f"App: {row.name} (category: {row.category})\n\n{blocks}"
    pass2: ExtractionResult = await extract(AUDIT_SYSTEM, user,
                                            ExtractionResult,
                                            prefer=VERIFY_MODEL)

    disputed: list[FieldDiff] = []
    for f in FIELDS:
        p1, p2 = _enc(row.result, f), _enc(pass2, f)
        d = FieldDiff(field=f, pass1=p1, pass2=p2, agreed=p1 == p2,
                      final=p1, resolution="agreed")
        out.diffs.append(d)
        if p1 != p2:
            disputed.append(d)

    if disputed:  # one tie-break call resolves all disputed fields at once
        claims = "\n".join(f"- {d.field}: pass1={d.pass1} pass2={d.pass2}"
                           for d in disputed)
        try:
            res: _Resolutions = await extract(
                TIEBREAK_SYSTEM,
                f"App: {row.name}\nDisputed fields:\n{claims}\n\n{blocks}",
                _Resolutions, prefer=VERIFY_MODEL)
            verdicts = {r.field: r for r in res.resolutions}
        except LLMError:
            verdicts = {}         # unresolved -> conservatively keep pass 1
        for d in disputed:
            v = verdicts.get(d.field)
            if v and v.winner == "pass2":
                d.final, d.resolution = d.pass2, "corrected_to_pass2"
            else:
                d.resolution = "kept_pass1"
            d.quote = v.quote if v else None
    return out


def _apply(done: dict[str, AppResearch], vs: list[AppVerification]) -> None:
    """Write corrections into rows, regenerate results + verification.json."""
    corrected = 0
    for v in vs:
        row = done.get(v.id)
        for d in v.diffs:
            if d.resolution == "corrected_to_pass2" and row and row.result:
                setattr(row.result, d.field, json.loads(d.final))
                corrected += 1
    assemble_results(done)

    total = sum(len(v.diffs) for v in vs)
    agreed = sum(d.agreed for v in vs for d in v.diffs)
    VERIFICATION_FILE.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fields_compared": total,
        "pass1_agreement": round(agreed / total, 4) if total else None,
        "corrections_applied": corrected,
        "apps": [v.model_dump(mode="json") for v in vs],
    }, indent=2))
    print(f"agreement {agreed}/{total}, corrected {corrected} field(s)")


RECHECK_ROUNDS = 3      # initial pass + up to 2 automatic recheck rounds
RECHECK_WAIT = 75       # seconds between rounds: lets per-minute quotas refill


def _retryable(v: AppVerification) -> bool:
    """Transient LLM failures (throttle/quota) deserve an automatic recheck;
    permanent skips (no pass-1 result, dead evidence pages) do not."""
    return bool(v.skipped and v.skipped.startswith("verify failed"))


async def run_verification() -> None:
    done = load_checkpoints()
    seen: dict[str, AppVerification] = {}
    if VERIFY_CKPT.exists():
        for line in VERIFY_CKPT.read_text().splitlines():
            if line.strip():
                v = AppVerification.model_validate_json(line)
                seen[v.id] = v

    sem, lock = asyncio.Semaphore(4), asyncio.Lock()

    async def worker(row: AppResearch) -> None:
        async with sem:
            try:
                v = await verify_app(row)
            except Exception as e:  # any failure: skip THIS app, keep batch
                v = AppVerification(id=row.id, name=row.name,
                                    skipped=f"verify failed: {e}")
        async with lock:
            with VERIFY_CKPT.open("a") as f:
                f.write(v.model_dump_json() + "\n")
        seen[row.id] = v
        n = sum(not d.agreed for d in v.diffs)
        print(f"[{len(seen)}/{len(done)}] {row.name}: "
              f"{v.skipped or f'{n} disagreement(s)'}")

    for rnd in range(1, RECHECK_ROUNDS + 1):
        todo = [r for r in done.values()
                if r.id not in seen or _retryable(seen[r.id])]
        if not todo:
            break
        if rnd == 1:
            print(f"{len(seen)} verified, {len(todo)} to verify")
        else:
            print(f"recheck round {rnd}: {len(todo)} transient failure(s)")
            await asyncio.sleep(RECHECK_WAIT)
        await asyncio.gather(*(worker(r) for r in todo))
    _apply(done, list(seen.values()))


if __name__ == "__main__":
    asyncio.run(run_verification())
