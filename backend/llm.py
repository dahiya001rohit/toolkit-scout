"""Thin Groq wrapper. One entry point — extract() — which always returns a
validated pydantic model or raises LLMError. All prompts go through here, so
retries, rate-limit handling and concurrency capping live in one place.

Groq free-tier quotas are PER MODEL (tokens/day). So instead of one model we
keep a preference-ordered pool: when a model's daily budget is exhausted
(TPD 429) we mark it dead for this process and rotate to the next."""

import asyncio
import json
import os

from dotenv import load_dotenv
from groq import AsyncGroq, RateLimitError
from pydantic import BaseModel, ValidationError

load_dotenv()  # local dev: pulls GROQ_API_KEY from .env; no-op in prod

# Preference order: strongest first. Overridable via env without code changes.
MODEL_POOL = [m.strip() for m in os.getenv(
    "GROQ_MODELS",
    "openai/gpt-oss-120b,llama-3.3-70b-versatile,qwen/qwen3-32b,"
    "meta-llama/llama-4-scout-17b-16e-instruct",
).split(",")]

# Models whose daily token budget ran out (process lifetime — the window is
# rolling, so a fresh run may find them alive again).
_exhausted: set[str] = set()

# Cap concurrent Groq calls project-wide so the parallel pipeline doesn't
# turn into a per-minute 429 storm.
_semaphore = asyncio.Semaphore(int(os.getenv("GROQ_MAX_CONCURRENCY", "4")))

_client: AsyncGroq | None = None


class LLMError(Exception):
    """Raised when no schema-valid output could be produced."""


def _get_client() -> AsyncGroq:
    # Lazy init so importing this module never requires the key to be set.
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def _pick_model(prefer: str | None) -> str | None:
    """First non-exhausted model; `prefer` (if given and alive) wins."""
    pool = ([prefer] if prefer else []) + MODEL_POOL
    for m in pool:
        if m not in _exhausted:
            return m
    return None


def _is_daily_quota(err: RateLimitError) -> bool:
    """TPD quota (rotate model) vs per-minute throttle (just wait)."""
    text = str(err)
    return "TPD" in text or "per day" in text


async def extract(system: str, user: str, schema: type[BaseModel],
                  retries: int = 2, prefer: str | None = None) -> BaseModel:
    """Call Groq in JSON mode and validate the reply into `schema`.

    json_object mode guarantees valid JSON, not our fields — so the schema is
    embedded in the prompt and pydantic enforces it. Validation failures are
    fed back for a corrective retry; daily-quota 429s rotate the model pool.
    `prefer` lets callers (e.g. cross-model verification) request a model.
    """
    schema_json = json.dumps(schema.model_json_schema())
    messages = [
        {"role": "system", "content":
            f"{system}\n\nRespond ONLY with a JSON object matching this "
            f"JSON Schema:\n{schema_json}"},
        {"role": "user", "content": user},
    ]

    last_err: Exception | None = None
    attempt = 0       # validation attempts (the model's fault)
    throttles = 0     # per-minute 429 waits (nobody's fault, but capped)
    while attempt <= retries and throttles < 6:
        model = _pick_model(prefer)
        if model is None:
            raise LLMError(f"all models exhausted: {MODEL_POOL}")
        try:
            async with _semaphore:
                resp = await _get_client().chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,  # extraction, not creativity
                )
            raw = resp.choices[0].message.content or ""
            return schema.model_validate_json(raw)

        except RateLimitError as e:
            last_err = e
            if _is_daily_quota(e):
                _exhausted.add(model)   # dead for this run -> rotate
                if prefer == model:
                    prefer = None
            else:
                throttles += 1          # brief wait, same model
                await asyncio.sleep(15 * throttles)

        except (ValidationError, json.JSONDecodeError) as e:
            # Malformed output: show the model its own mistake and retry.
            last_err = e
            attempt += 1
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Invalid response, fix these errors and resend "
                           f"the full corrected JSON only: {e}",
            })

    raise LLMError(f"LLM failed (attempts={attempt}, throttles={throttles}): "
                   f"{last_err}")
