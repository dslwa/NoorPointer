import asyncio

from app.detectors.base import Detector
from app.schemas import CheckResult, ScanRequest

MAX_TOKENS = 512
STRIDE = 64
BATCH = 16


class PromptInjectionDetector(Detector):
    """DeBERTa classifier. Long texts are split into overlapping windows and the worst window wins,
    so an injection hidden at the end of a long document is not truncated away."""

    name = "prompt_injection"

    def __init__(self, model_id: str, torch_threads: int, offline: bool = False) -> None:
        super().__init__()
        self.model_id = model_id
        self.torch_threads = torch_threads
        self.offline = offline  # load from the baked-in cache only; scoped here, so HF repo scanning still works

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        torch.set_num_threads(self.torch_threads)
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, local_files_only=self.offline)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.model_id, local_files_only=self.offline).eval()
        labels = {label.upper(): idx for idx, label in self.model.config.id2label.items()}
        self.injection_idx = next(idx for label, idx in labels.items() if "INJECTION" in label)
        self._score("warm up")

    def _score(self, text: str) -> tuple[float, int, int]:
        enc = self.tokenizer(
            text,
            truncation=True,
            max_length=MAX_TOKENS,
            stride=STRIDE,
            return_overflowing_tokens=True,
            padding=True,
            return_tensors="pt",
        )
        enc.pop("overflow_to_sample_mapping", None)
        windows = enc["input_ids"].shape[0]
        best_score, best_window = 0.0, 0
        with self.torch.inference_mode():
            for start in range(0, windows, BATCH):
                batch = {k: v[start : start + BATCH] for k, v in enc.items()}
                probs = self.model(**batch).logits.softmax(-1)[:, self.injection_idx]
                idx = int(probs.argmax())
                if float(probs[idx]) > best_score:
                    best_score, best_window = float(probs[idx]), start + idx
        return best_score, best_window, windows

    async def check(self, req: ScanRequest) -> CheckResult:
        score, window, windows = await asyncio.to_thread(self._score, req.text)
        return CheckResult(
            check=self.name,
            status="ok",
            flagged=score >= req.config.prompt_injection.threshold,
            score=round(score, 4),
            details={"windows": windows, "worst_window": window, "model": self.model_id},
        )
