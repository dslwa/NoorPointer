import asyncio

from app.detectors.base import Detector
from app.schemas import CheckResult, ScanRequest

PESEL_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
# Not personal data, and spaCy tags them very noisily ("Q3", "AI", e-mail domains). Still available on request.
NOISY_ENTITIES = {"ORGANIZATION", "URL"}


def valid_pesel(value: str) -> bool:
    if len(value) != 11 or not value.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(value, PESEL_WEIGHTS))
    return (10 - total % 10) % 10 == int(value[10])


class PiiDetector(Detector):
    """Presidio (spaCy NER + pattern recognizers) for PII in natural language, plus a Polish PESEL recognizer.
    Finding details never include the matched values, so audit logs don't become a PII store themselves."""

    name = "pii_ner"

    def __init__(self, spacy_model: str) -> None:
        super().__init__()
        self.spacy_model = spacy_model

    def _load(self) -> None:
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer import AnonymizerEngine

        class PeselRecognizer(PatternRecognizer):
            def validate_result(self, pattern_text: str) -> bool:
                return valid_pesel(pattern_text)

        nlp = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": self.spacy_model}],
            }
        ).create_engine()
        self.analyzer = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
        self.analyzer.registry.add_recognizer(
            PeselRecognizer(
                supported_entity="PL_PESEL",
                patterns=[Pattern("pesel", r"\b\d{11}\b", 0.4)],
                context=["pesel"],
            )
        )
        self.anonymizer = AnonymizerEngine()
        self.default_entities = sorted(set(self.analyzer.get_supported_entities("en")) - NOISY_ENTITIES)
        self._analyze("warm up John Smith", None, 0.5)

    def _analyze(self, text: str, entities: list[str] | None, threshold: float):
        results = self.analyzer.analyze(text=text, language="en", entities=entities or self.default_entities,
                                        score_threshold=threshold)
        redacted = self.anonymizer.anonymize(text=text, analyzer_results=results).text
        return results, redacted

    async def check(self, req: ScanRequest) -> CheckResult:
        cfg = req.config.pii_ner
        results, redacted = await asyncio.to_thread(self._analyze, req.text, cfg.entities, cfg.score_threshold)
        findings = sorted(
            ({"type": r.entity_type, "start": r.start, "end": r.end, "score": round(r.score, 3)} for r in results),
            key=lambda f: f["start"],
        )
        return CheckResult(
            check=self.name,
            status="ok",
            flagged=bool(findings),
            score=max((f["score"] for f in findings), default=0.0),
            details={
                "entities": findings,
                "counts": {t: sum(f["type"] == t for f in findings) for t in {f["type"] for f in findings}},
                "redacted_text": redacted,
            },
        )
