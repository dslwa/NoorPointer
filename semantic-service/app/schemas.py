from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

MAX_TEXT_CHARS = 200_000
MAX_CANARIES = 100
MAX_CANARY_CHARS = 256

CheckName = Literal["prompt_injection", "content_safety", "pii_ner", "leakage"]
Direction = Literal["input", "output"]
# ok      - check ran; see `flagged`
# skipped - check does not apply (e.g. leakage on an input)
# timeout - check exceeded timeout_ms; the gateway applies on_semantic_timeout (fail_open/fail_closed)
# error   - check failed or its model is not ready; gateway should treat like timeout
# rejected - input broke a hard limit; attacker-triggerable, so the gateway must always block (never fail open)
Status = Literal["ok", "skipped", "timeout", "error", "rejected"]


class PromptInjectionConfig(BaseModel):
    threshold: float = Field(0.85, ge=0, le=1)


class ContentSafetyConfig(BaseModel):
    # Llama Guard 3 hazard codes (S1..S14). None = every unsafe category counts.
    categories: list[str] | None = None


class PiiConfig(BaseModel):
    # Presidio entity types, e.g. PERSON, EMAIL_ADDRESS, IBAN_CODE, CREDIT_CARD, PL_PESEL. None = all.
    entities: list[str] | None = None
    score_threshold: float = Field(0.5, ge=0, le=1)
    redact: bool = True  # also produce redacted_text (the gRPC path only needs spans)


class LeakageConfig(BaseModel):
    ngram: int = Field(6, ge=2, le=20)
    threshold: float = Field(0.15, ge=0, le=1)


class ChecksConfig(BaseModel):
    prompt_injection: PromptInjectionConfig = Field(default_factory=PromptInjectionConfig)
    content_safety: ContentSafetyConfig = Field(default_factory=ContentSafetyConfig)
    pii_ner: PiiConfig = Field(default_factory=PiiConfig)
    leakage: LeakageConfig = Field(default_factory=LeakageConfig)


def _valid_utf8(value):
    """Lone UTF-16 surrogates (e.g. a JSON "\\ud800" escape) are not text: the tokenizer and httpx raise on
    them, which would turn attacker input into STATUS_ERROR. Replace them so the rest is still analysed."""
    if isinstance(value, str):
        return value.encode("utf-8", "replace").decode("utf-8")
    if isinstance(value, list):
        return [_valid_utf8(v) for v in value]
    return value


class ScanContext(BaseModel):
    system_prompt: str | None = Field(None, max_length=MAX_TEXT_CHARS)
    canaries: list[Annotated[str, Field(max_length=MAX_CANARY_CHARS)]] = Field(default_factory=list,
                                                                               max_length=MAX_CANARIES)
    # For direction=output: the user prompt that produced the response (Llama Guard rates the reply in context).
    prompt: str | None = Field(None, max_length=MAX_TEXT_CHARS)

    _utf8 = field_validator("system_prompt", "canaries", "prompt", mode="before")(_valid_utf8)


class ScanRequest(BaseModel):
    request_id: str | None = None
    direction: Direction = "input"
    text: str = Field(max_length=MAX_TEXT_CHARS)
    checks: list[CheckName] | None = None
    config: ChecksConfig = Field(default_factory=ChecksConfig)
    context: ScanContext = Field(default_factory=ScanContext)
    timeout_ms: int = Field(1000, ge=10, le=30_000)

    _utf8 = field_validator("text", mode="before")(_valid_utf8)


class CheckResult(BaseModel):
    check: CheckName
    status: Status
    flagged: bool = False
    score: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0
    error: str | None = None


class ScanResponse(BaseModel):
    request_id: str | None
    flagged: bool
    results: list[CheckResult]
    # Present when the pii check ran: text with entities replaced by <ENTITY_TYPE>.
    redacted_text: str | None = None
    latency_ms: float


class HfScanRequest(BaseModel):
    repo_id: str = Field(pattern=r"^(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/)?[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
    revision: str | None = Field(None, pattern=r"^[A-Za-z0-9_./-]{1,255}$")
