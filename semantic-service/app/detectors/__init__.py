import httpx

from app.config import Settings
from app.detectors.base import Detector
from app.detectors.content_safety import ContentSafetyDetector
from app.detectors.leakage import LeakageDetector
from app.detectors.pii import PiiDetector
from app.detectors.prompt_injection import PromptInjectionDetector


def build_detectors(settings: Settings, client: httpx.AsyncClient) -> dict[str, Detector]:
    factories = {
        "prompt_injection": lambda: PromptInjectionDetector(settings.pi_model, settings.torch_threads, settings.models_offline),
        "content_safety": lambda: ContentSafetyDetector(client, settings.ollama_url, settings.guard_model),
        "pii_ner": lambda: PiiDetector(settings.spacy_model),
        "leakage": LeakageDetector,
    }
    return {name: factories[name]() for name in settings.enabled_checks if name in factories}
