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
    ollama_url: str = "http://localhost:11434"
    guard_model: str = "llama-guard3:1b"
    torch_threads: int = 4
    max_upload_mb: int = 512
    max_unpacked_mb: int = 1024  # decompression budget for archives (zip bombs)
    models_offline: bool = False  # load inference models from the local cache only (set in Docker)
    grpc_port: int = 50051  # 0 disables the gRPC server
    artifact_root: str = "/artifacts"  # shared volume for ScanArtifact(path=...)
    artifact_hosts: list[str] = field(default_factory=lambda: ["huggingface.co", "hf.co"])  # + subdomains

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            enabled_checks=_env_list("ENABLED_CHECKS", list(ALL_CHECKS)),
            pi_model=os.getenv("PI_MODEL", cls.pi_model),
            spacy_model=os.getenv("SPACY_MODEL", cls.spacy_model),
            ollama_url=os.getenv("OLLAMA_URL", cls.ollama_url).rstrip("/"),
            guard_model=os.getenv("GUARD_MODEL", cls.guard_model),
            torch_threads=int(os.getenv("TORCH_THREADS", cls.torch_threads)),
            max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", cls.max_upload_mb)),
            max_unpacked_mb=int(os.getenv("MAX_UNPACKED_MB", cls.max_unpacked_mb)),
            models_offline=os.getenv("MODELS_OFFLINE", "0").lower() in ("1", "true", "yes"),
            grpc_port=int(os.getenv("GRPC_PORT", cls.grpc_port)),
            artifact_root=os.getenv("ARTIFACT_ROOT", cls.artifact_root),
            artifact_hosts=_env_list("ARTIFACT_HOSTS", ["huggingface.co", "hf.co"]),
        )
