import time

from app.detectors.base import CostModel, Detector
from app.schemas import CheckResult, ScanRequest
from app.workers import BoundedWorkers

# Small enough that one segment (always attempted) stays cheap even for text that costs ~10x the average
# per character, e.g. long digit runs; longer text is several segments, checked against the budget.
SEGMENT_CHARS = 2_000
SEGMENT_OVERLAP = 200  # longer than any name, e-mail or account number
PESEL_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
# Not personal data, and spaCy tags them very noisily ("Q3", "AI", e-mail domains). Still available on request.
NOISY_ENTITIES = {"ORGANIZATION", "URL"}


def redact_spans(text: str, results) -> str:
    """Replace each entity with <TYPE>; where entities overlap, the earlier (then longer) one wins. Linear
    after sorting: Presidio's anonymizer resolves overlaps pairwise, which a text crafted to contain thousands
    of entities turns into seconds of work."""
    out, pos = [], 0
    for r in sorted(results, key=lambda r: (r.start, -(r.end - r.start))):
        if r.start < pos:
            continue  # overlaps an entity already replaced
        out += [text[pos : r.start], f"<{r.entity_type}>"]
        pos = r.end
    out.append(text[pos:])
    return "".join(out)


def valid_pesel(value: str) -> bool:
    if len(value) != 11 or not value.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(value, PESEL_WEIGHTS))
    return (10 - total % 10) % 10 == int(value[10])


class PiiDetector(Detector):
    """Presidio (spaCy NER + pattern recognizers) for PII in natural language, plus a Polish PESEL recognizer.
    Finding details never include the matched values, so audit logs don't become a PII store themselves."""

    name = "pii_ner"

    def __init__(self, spacy_model: str, workers: int = 4) -> None:
        super().__init__()
        self.workers = BoundedWorkers("pii", workers)
        self.cost = CostModel(min_units=1000)  # seconds per character
        self.spacy_model = spacy_model

    def _load(self) -> None:
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        from presidio_analyzer.nlp_engine import NlpEngineProvider

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
        self.default_entities = sorted(set(self.analyzer.get_supported_entities("en")) - NOISY_ENTITIES)
        self._analyze("warm up John Smith", None, 0.5, None)  # cold, and too small to count
        self._analyze("The meeting with the treasury team is at noon. " * 200, None, 0.5, None, False)  # calibrate

    def _analyze(self, text: str, entities: list[str] | None, threshold: float, deadline: float | None,
                 redact: bool = True, budget_s: float | None = None):
        """Analyze in overlapping segments, checking the deadline between them, so a timed-out check frees its
        worker within one segment instead of finishing a 200k-char text. Each entity belongs to the segment it
        starts in (an entity shorter than the overlap is whole there), and a segment that begins in the middle of
        an entity the previous one kept drops that fragment, so nothing is reported twice."""
        from presidio_analyzer import RecognizerResult

        starts = list(range(0, max(len(text) - SEGMENT_OVERLAP, 1), SEGMENT_CHARS - SEGMENT_OVERLAP))
        what = f"PII scan of {len(text)} chars"
        if deadline is not None:
            self.cost.refuse_if_too_big(len(text), budget_s, deadline, len(starts) > 1, what)
        results, previous = [], []
        run_started, done_chars = time.monotonic(), 0
        for i, start in enumerate(starts):
            owned_until = starts[i + 1] if i + 1 < len(starts) else len(text)
            segment = text[start : start + SEGMENT_CHARS]
            if deadline is not None and i > 0:
                run_rate = (time.monotonic() - run_started) / done_chars if done_chars else None
                self.cost.refuse_next(len(segment), deadline, what, run_rate)
            segment_started = time.monotonic()
            found = self.analyzer.analyze(text=segment, language="en", entities=entities or self.default_entities,
                                          score_threshold=threshold)
            if len(segment) >= 1000:  # tiny texts are dominated by fixed overhead and would skew the estimate
                self.cost.observe(len(segment), time.monotonic() - segment_started)
            done_chars += len(segment)
            crossing = [p for p in previous if p.end > start]  # previous entities reaching into this segment
            current = []
            for r in found:
                begin, end = start + r.start, start + r.end
                # a fragment of an entity the previous segment kept has the same type and overlaps it; an
                # overlapping entity of another type is a separate finding and must not be dropped
                duplicate = any(p.entity_type == r.entity_type and p.start < end and begin < p.end for p in crossing)
                if begin >= owned_until or duplicate:
                    continue
                current.append(RecognizerResult(r.entity_type, begin, end, r.score))
            results += current
            previous = current
        return results, (redact_spans(text, results) if redact else None)

    async def check(self, req: ScanRequest) -> CheckResult:
        cfg = req.config.pii_ner
        budget = req.timeout_ms / 1000
        deadline = time.monotonic() + budget
        results, redacted = await self.workers.run(self._analyze, req.text, cfg.entities, cfg.score_threshold,
                                                   deadline, cfg.redact, budget)
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
