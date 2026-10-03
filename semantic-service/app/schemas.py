from typing import Any, Literal

from pydantic import BaseModel, Field

CheckName = Literal["prompt_injection", "content_safety", "pii_ner", "leakage"]
Direction = Literal["input", "output"]
# ok      - check ran; see `flagged`
# skipped - check does not apply (e.g. leakage on an input)
# timeout - check exceeded timeout_ms; the gateway applies on_semantic_timeout (fail_open/fail_closed)
# error   - check failed or its model is not ready; gateway should treat like timeout
Status = Literal["ok", "skipped", "timeout", "error"]


class PromptInjectionConfig(BaseModel):
    threshold: float = Field(0.85, ge=0, le=1)


class ContentSafetyConfig(BaseModel):
    # Llama Guard 3 hazard codes (S1..S14). None = every unsafe category counts.
    categories: list[str] | None = None


class PiiConfig(BaseModel):
    # Presidio entity types, e.g. PERSON, EMAIL_ADDRESS, IBAN_CODE, CREDIT_CARD, PL_PESEL. None = all.
    entities: list[str] | None = None
    score_threshold: float = Field(0.5, ge=0, le=1)


class LeakageConfig(BaseModel):
    ngram: int = Field(6, ge=2, le=20)
    threshold: float = Field(0.15, ge=0, le=1)


class ChecksConfig(BaseModel):
    prompt_injection: PromptInjectionConfig = Field(default_factory=PromptInjectionConfig)
    content_safety: ContentSafetyConfig = Field(default_factory=ContentSafetyConfig)
    pii_ner: PiiConfig = Field(default_factory=PiiConfig)
    leakage: LeakageConfig = Field(default_factory=LeakageConfig)


class ScanContext(BaseModel):
    system_prompt: str | None = None
    canaries: list[str] = Field(default_factory=list)
    # For direction=output: the user prompt that produced the response (Llama Guard rates the reply in context).
    prompt: str | None = None


class ScanRequest(BaseModel):
    request_id: str | None = None
    direction: Direction = "input"
    text: str = Field(max_length=200_000)
    checks: list[CheckName] | None = None
    config: ChecksConfig = Field(default_factory=ChecksConfig)
    context: ScanContext = Field(default_factory=ScanContext)
    timeout_ms: int = Field(1000, ge=10, le=30_000)


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
    repo_id: str
    revision: str | None = None
