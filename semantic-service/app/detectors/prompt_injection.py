import time

from app.detectors.base import COST_MARGIN_S, CostModel, Detector, Rejected
from app.schemas import CheckResult, ScanRequest
from app.workers import BoundedWorkers

MAX_TOKENS = 512
WINDOW_BODY = MAX_TOKENS - 2  # room for [CLS] and [SEP]
STRIDE = 128  # tokens shared by neighbouring windows, so an injection on a window boundary is seen whole
BATCH = 16


def token_windows(ids: list[int], body: int = WINDOW_BODY, overlap: int = STRIDE) -> list[list[int]]:
    """Overlapping slices covering every token. Built here rather than with the tokenizer's
    return_overflowing_tokens: this model ships only the slow DeBERTa tokenizer, whose overflow returns a
    single extra chunk, so everything after the first ~900 tokens of a long text was never scanned."""
    step = body - overlap
    return [ids[start : start + body] for start in range(0, max(len(ids) - overlap, 1), step)]


class PromptInjectionDetector(Detector):
    """DeBERTa classifier. Long texts are split into overlapping windows and the worst window wins,
    so an injection hidden at the end of a long document is not truncated away."""

    name = "prompt_injection"

    def __init__(self, model_id: str, torch_threads: int, offline: bool = False, workers: int = 2) -> None:
        super().__init__()
        self.workers = BoundedWorkers("prompt-injection", workers)
        # seconds per (padded) token, learned from batches big enough to measure (a "window" can be 20 tokens)
        self.cost = CostModel(min_units=256)
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
        self._score("warm up", None, None)  # cold: too small to count towards the cost estimate
        self._score("calibration " * 600, None, None)  # warm, two full windows: a realistic first estimate

    def _encode(self, text: str):
        ids = self.tokenizer(text, add_special_tokens=False, verbose=False)["input_ids"]
        rows = [[self.tokenizer.cls_token_id, *w, self.tokenizer.sep_token_id] for w in token_windows(ids)]
        width = max(len(r) for r in rows)
        pad = self.tokenizer.pad_token_id
        input_ids = self.torch.tensor([r + [pad] * (width - len(r)) for r in rows])
        attention_mask = self.torch.tensor([[1] * len(r) + [0] * (width - len(r)) for r in rows])
        return {"input_ids": input_ids, "attention_mask": attention_mask}

    def _score(self, text: str, deadline: float | None, budget_s: float | None) -> tuple[float, int, int]:
        had_time = deadline is None or time.monotonic() < deadline
        enc = self._encode(text)
        windows, seq_len = enc["input_ids"].shape
        what = f"prompt-injection scan of {windows} windows"
        if deadline is not None and had_time and windows > 1 and time.monotonic() >= deadline - COST_MARGIN_S:
            raise Rejected(f"tokenizing this {len(text)}-char text used up the {budget_s * 1000:.0f} ms budget")
        if deadline is not None:
            self.cost.refuse_if_too_big(windows * seq_len, budget_s, deadline, windows > 1, what)
        best_score, best_window = 0.0, 0
        with self.torch.inference_mode():
            for start in range(0, windows, BATCH):
                batch = {k: v[start : start + BATCH] for k, v in enc.items()}
                if deadline is not None and start > 0:
                    self.cost.refuse_next(batch["input_ids"].numel(), deadline, what)
                batch_started = time.monotonic()
                probs = self.model(**batch).logits.softmax(-1)[:, self.injection_idx]
                self.cost.observe(batch["input_ids"].numel(), time.monotonic() - batch_started)
                idx = int(probs.argmax())
                if float(probs[idx]) > best_score:
                    best_score, best_window = float(probs[idx]), start + idx
        return best_score, best_window, windows

    async def check(self, req: ScanRequest) -> CheckResult:
        budget = req.timeout_ms / 1000
        deadline = time.monotonic() + budget
        score, window, windows = await self.workers.run(self._score, req.text, deadline, budget)
        return CheckResult(
            check=self.name,
            status="ok",
            flagged=score >= req.config.prompt_injection.threshold,
            score=round(score, 4),
            details={"windows": windows, "worst_window": window, "model": self.model_id},
        )
