"""Single-app researcher: find docs URLs -> fetch real pages -> extract a
schema-valid answer grounded ONLY in fetched text. The one 'agentic' branch:
when normal URL discovery finds nothing, the LLM proposes where to look next
(safe — a bad guess just fails to fetch; answers never come from memory)."""

import asyncio
import re
from datetime import datetime, timezone
from typing import Awaitable, Callable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

from .llm import LLMError, extract
from .schemas import AppInput, AppResearch, ExtractionResult

HEADERS = {"User-Agent": "toolkit-scout/1.0 (API docs research; contact via repo)"}
PAGE_CHAR_LIMIT = 4000   # per-page text sent to the LLM (token budget)
MAX_PAGES = 3            # stop fetching once this many pages succeed

# Where API docs conventionally live, tried against the app's root domain.
DOC_SUBDOMAINS = ["developers.{d}", "docs.{d}", "developer.{d}", "api.{d}"]
DOC_PATHS = ["{d}/api", "{d}/developers"]

EXTRACT_SYSTEM = (
    "You are an analyst researching whether an app's public API can back an "
    "AI-agent toolkit. Answer using ONLY the page text provided by the user. "
    "The description must say what the product specifically does, taken from "
    "the text — never a restatement of its category. "
    "Hard rules: if the text does not contain an answer, use 'unknown' (or "
    "null for evidence URLs) — never answer from memory, never invent APIs, "
    "endpoints or auth methods. Each *_evidence_url must be one of the "
    "provided SOURCE urls, chosen because its text supports that answer. "
    "Set has_mcp=true only if the text explicitly mentions an MCP server."
)

ProgressFn = Callable[[str], Awaitable[None]]


class _UrlGuesses(BaseModel):
    """Tiny schema for the agentic fallback: LLM proposes docs URLs to try."""
    urls: list[str]


async def _emit(progress: ProgressFn | None, msg: str) -> None:
    if progress:
        await progress(msg)


def _root_domain(hint: str) -> str | None:
    """'developers.klaviyo.com/foo' -> 'klaviyo.com'; None if hint isn't a URL."""
    if " " in hint or "." not in hint:
        return None
    host = hint.split("/")[0]
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _candidate_urls(app: AppInput) -> list[str]:
    """Ordered fetch candidates: given hint first, then conventional guesses."""
    urls: list[str] = []
    if _root_domain(app.hint):  # hint is URL-like -> best first candidate
        urls.append(f"https://{app.hint}")
    root = _root_domain(app.hint)
    if root:
        urls += [f"https://{p.format(d=root)}" for p in DOC_SUBDOMAINS]
        urls.append(f"https://{root}")  # homepage (also feeds the link scan)
        urls += [f"https://{p.format(d=root)}" for p in DOC_PATHS]
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def _docs_links_from_html(base_url: str, html: str) -> list[str]:
    """Scan a fetched page for links that look like API/developer docs."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        blob = (a["href"] + " " + a.get_text()).lower()
        if re.search(r"\bapi\b|developer|docs|documentation", blob):
            found.append(urljoin(base_url, a["href"]))
    return found[:5]


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()[:PAGE_CHAR_LIMIT]


async def _fetch(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    """GET url -> (final_url, raw_html) or None. Never raises."""
    try:
        r = await client.get(url, timeout=15, follow_redirects=True,
                             headers=HEADERS)
        if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
            return str(r.url), r.text
    except httpx.HTTPError:
        pass
    return None


async def _gather_pages(app: AppInput, client: httpx.AsyncClient,
                        progress: ProgressFn | None) -> dict[str, str]:
    """Try candidates in order until MAX_PAGES fetch; returns {url: text}."""
    pages: dict[str, str] = {}
    queue = _candidate_urls(app)
    tried: set[str] = set()
    while queue and len(pages) < MAX_PAGES:
        url = queue.pop(0)
        if url in tried:
            continue
        tried.add(url)
        await _emit(progress, f"fetching {url}")
        hit = await _fetch(client, url)
        if not hit:
            continue
        final_url, html = hit
        pages[final_url] = _html_to_text(html)
        # docs-looking links found on any successful page join the queue
        queue += [u for u in _docs_links_from_html(final_url, html)
                  if u not in tried]

    if not pages:  # agentic fallback: ask the LLM where these docs might live
        await _emit(progress, "no pages found — asking LLM for likely doc URLs")
        try:
            guess = await extract(
                "Suggest up to 4 likely official API-documentation URLs for "
                "the given app. Output urls only.",
                f"App: {app.name}. Known hint: {app.hint}", _UrlGuesses)
            for url in guess.urls[:4]:
                if len(pages) >= MAX_PAGES:
                    break
                await _emit(progress, f"trying LLM guess {url}")
                hit = await _fetch(client, url)
                if hit:
                    pages[hit[0]] = _html_to_text(hit[1])
        except LLMError:
            pass  # fallback failing just means pages stays empty
    return pages


async def research_app(app: AppInput,
                       progress: ProgressFn | None = None) -> AppResearch:
    """Full research for one app. Always returns a row — never raises."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = AppResearch(id=app.id, name=app.name, category=app.category,
                      hint=app.hint, researched_at=now)
    async with httpx.AsyncClient() as client:
        pages = await _gather_pages(app, client, progress)
    row.sources_fetched = list(pages)

    if not pages:  # honest failure — the correct answer for some trap apps
        row.error = "no documentation pages could be fetched"
        return row

    blocks = "\n\n".join(f"SOURCE: {u}\n{t}" for u, t in pages.items())
    await _emit(progress, f"extracting from {len(pages)} page(s)")
    try:
        row.result = await extract(
            EXTRACT_SYSTEM,
            f"App: {app.name} (category: {app.category})\n\n{blocks}",
            ExtractionResult)
    except LLMError as e:
        row.error = f"extraction failed: {e}"
    return row
