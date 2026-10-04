import os
from dataclasses import dataclass, field

ALL_CHECKS = ["prompt_injection", "content_safety", "pii_ner", "leakage"]


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    enabled_checks: list[str] = field(default_factory=lambda: list(ALL_CHECKS))
    pi_model: str = "protectai/deberta-v3-base-prompt-injection-v2"
    spacy_model: str = "en_core_web_lg"
    spacy_model_pl: str = "pl_core_news_lg"  # empty disables Polish NER
    ollama_url: str = "http://localhost:11434"
    guard_model: str = "llama-guard3:1b"
    guard_concurrency: int = 4
    torch_threads: int = 4
    max_upload_mb: int = 512
    max_unpacked_mb: int = 1024  # decompression budget for archives (zip bombs)
    models_offline: bool = False  # load inference models from the local cache only (set in Docker)
    pi_workers: int = 2  # concurrent prompt-injection inferences (each uses torch_threads)
    pii_workers: int = 4
    leakage_workers: int = 2
    scan_workers: int = 2  # concurrent artifact scans; memory bound ~ scan_workers x (max_upload + max_unpacked)
    max_messages: int = 64  # per Analyze call
    max_request_chars: int = 1_000_000  # per Analyze call, summed over messages
    grpc_port: int = 50051  # 0 disables the gRPC server
    artifact_root: str = "/artifacts"  # shared volume for ScanArtifact(path=...)
    artifact_hosts: list[str] = field(default_factory=lambda: ["huggingface.co", "hf.co"])  # + subdomains

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            enabled_checks=_env_list("ENABLED_CHECKS", list(ALL_CHECKS)),
            pi_model=os.getenv("PI_MODEL", cls.pi_model),
            spacy_model=os.getenv("SPACY_MODEL", cls.spacy_model),
            spacy_model_pl=os.getenv("SPACY_MODEL_PL", cls.spacy_model_pl),
            ollama_url=os.getenv("OLLAMA_URL", cls.ollama_url).rstrip("/"),
            guard_model=os.getenv("GUARD_MODEL", cls.guard_model),
            guard_concurrency=int(os.getenv("GUARD_CONCURRENCY", cls.guard_concurrency)),
            torch_threads=int(os.getenv("TORCH_THREADS", cls.torch_threads)),
            max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", cls.max_upload_mb)),
            max_unpacked_mb=int(os.getenv("MAX_UNPACKED_MB", cls.max_unpacked_mb)),
            models_offline=os.getenv("MODELS_OFFLINE", "0").lower() in ("1", "true", "yes"),
            pi_workers=int(os.getenv("PI_WORKERS", cls.pi_workers)),
            pii_workers=int(os.getenv("PII_WORKERS", cls.pii_workers)),
            leakage_workers=int(os.getenv("LEAKAGE_WORKERS", cls.leakage_workers)),
            scan_workers=int(os.getenv("SCAN_WORKERS", cls.scan_workers)),
            max_messages=int(os.getenv("MAX_MESSAGES", cls.max_messages)),
            max_request_chars=int(os.getenv("MAX_REQUEST_CHARS", cls.max_request_chars)),
            grpc_port=int(os.getenv("GRPC_PORT", cls.grpc_port)),
            artifact_root=os.getenv("ARTIFACT_ROOT", cls.artifact_root),
            artifact_hosts=_env_list("ARTIFACT_HOSTS", ["huggingface.co", "hf.co"]),
        )
