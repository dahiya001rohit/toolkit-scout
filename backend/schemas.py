"""Pydantic models — the single contract shared by the agent, pipeline,
verifier, API and frontend. Every LLM response is validated against
ExtractionResult; anything malformed is rejected and retried."""

from enum import Enum
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums — fixed vocabularies so results can be counted/clustered downstream.
# "unknown" is always a legal answer: the prompt tells the LLM to use it
# instead of guessing when the fetched text doesn't contain the answer.
# ---------------------------------------------------------------------------

class AuthMethod(str, Enum):
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BASIC = "basic"            # username/password or email/token Basic auth
    TOKEN = "token"            # static bearer/personal-access tokens
    OTHER = "other"            # HMAC signing, JWT service accounts, etc.
    NONE = "none"              # no API at all -> no auth to speak of
    UNKNOWN = "unknown"


class Access(str, Enum):
    SELF_SERVE = "self_serve"          # free dev credentials, no human in loop
    TRIAL = "trial"                    # credentials via free trial signup
    PAID = "paid"                      # API only on a paid plan
    PARTNER_GATED = "partner_gated"    # approval / contact-sales / partnership
    UNKNOWN = "unknown"


class ApiType(str, Enum):
    REST = "rest"
    GRAPHQL = "graphql"
    BOTH = "both"
    OTHER = "other"            # SOAP, gRPC, websocket-only, CLI-only...
    NONE = "none"
    UNKNOWN = "unknown"


class ApiBreadth(str, Enum):
    BROAD = "broad"            # covers most of the product's objects/actions
    MODERATE = "moderate"      # core objects only, notable gaps
    NARROW = "narrow"          # a handful of endpoints
    NONE = "none"
    UNKNOWN = "unknown"


class Buildability(str, Enum):
    READY = "ready"                          # toolkit buildable today
    PARTIAL = "partial"                      # buildable with workarounds
    BLOCKED_NO_API = "blocked_no_api"        # no public API exists
    BLOCKED_GATED = "blocked_gated"          # API exists but access is gated
    BLOCKED_THIN_DOCS = "blocked_thin_docs"  # docs too thin/absent to build on


class Confidence(str, Enum):
    HIGH = "high"        # answers grounded in official docs text
    MEDIUM = "medium"    # grounded, but docs were partial/ambiguous
    LOW = "low"          # little or nothing could be fetched


# ---------------------------------------------------------------------------
# Input — one entry of data/apps.json, verbatim from the assignment.
# ---------------------------------------------------------------------------

class AppInput(BaseModel):
    id: str                    # 6-char uuid, checkpoint key
    name: str
    category: str
    hint: str                  # website/hint as given; NOT guaranteed a URL


# ---------------------------------------------------------------------------
# ExtractionResult — exactly what the LLM must return (and nothing else).
# Per-field evidence URLs are separate on purpose: "docs URL behind each
# answer" is a hard requirement of the assignment.
# ---------------------------------------------------------------------------

class ExtractionResult(BaseModel):
    description: str = Field(description="What the app does, one line")
    auth_methods: list[AuthMethod]
    auth_evidence_url: str | None = None
    access: Access
    access_evidence_url: str | None = None
    api_type: ApiType
    api_breadth: ApiBreadth
    api_evidence_url: str | None = None
    has_mcp: bool | None = None          # None = couldn't determine
    mcp_evidence_url: str | None = None
    buildability: Buildability
    buildability_reason: str = Field(description="One-line justification")
    confidence: Confidence


# ---------------------------------------------------------------------------
# AppResearch — one finished row: input identity + extraction + run metadata.
# This is what checkpoints.jsonl stores and /data.json serves.
# ---------------------------------------------------------------------------

class AppResearch(BaseModel):
    id: str
    name: str
    category: str
    hint: str
    result: ExtractionResult | None = None   # None = research failed entirely
    sources_fetched: list[str] = []          # URLs whose text the LLM saw
    error: str | None = None                 # why result is None, honestly
    researched_at: str = ""                  # ISO timestamp
