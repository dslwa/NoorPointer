import logging
import threading
import time

from app.schemas import CheckResult, ScanRequest

log = logging.getLogger(__name__)


class Rejected(Exception):
    """The input breaks a hard limit of a check. Reported as status "rejected", which always blocks: an
    attacker could otherwise oversize content on purpose to get it through a fail-open policy unscanned."""


# Refuse work estimated to need more than this share of the check's budget: run-to-run variance must not
# turn an accepted job into a timeout an attacker can retry until it fails open.
COST_SAFETY = 0.8
# Raise our own verdict this long before the caller's timeout fires, so it is ours (REJECTED), not a timeout.
COST_MARGIN_S = 0.02


class CostModel:
    """Moving average of measured seconds per unit of work (token, character, Llama Guard call).

    Input size is attacker-controlled. If a check simply ran until its timeout, padding a payload would turn
    its verdict into STATUS_TIMEOUT, which a fail-open policy lets through. So:
      - work whose size cannot fit the check's budget (even with an idle service) is refused up front as
        Rejected, which always blocks;
      - work that would fit, but not in the time left after waiting for a busy worker, is a timeout: that's
        load, not the input;
      - multi-unit work that runs out of time partway is Rejected before the caller's timeout fires.
    Single-unit work is always attempted, so a lone short message that times out is load and stays a timeout.
    Nothing is refused on a guess: until something has been measured, only the deadline applies."""

    def __init__(self, min_units: float = 0, skip_first: int = 0) -> None:
        self.per_unit: float | None = None
        self._lock = threading.Lock()
        self._min_units = min_units  # smaller samples are dominated by fixed overhead and overstate the cost
        self._skip = skip_first  # e.g. a cold first call that includes loading the model

    def observe(self, units: float, seconds: float) -> None:
        if units <= 0 or units < self._min_units:
            return
        with self._lock:
            if self._skip > 0:
                self._skip -= 1
                return
            sample = seconds / units
            self.per_unit = sample if self.per_unit is None else 0.8 * self.per_unit + 0.2 * sample

    def refuse_if_too_big(self, units: float, budget_s: float, deadline: float, multi_unit: bool, what: str) -> None:
        """Before starting: budget_s is the check's whole timeout, deadline when it runs out."""
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("no time left after waiting for a worker")
        if not multi_unit or self.per_unit is None:
            return
        need = units * self.per_unit
        if need > COST_SAFETY * budget_s:
            raise Rejected(f"{what} needs ~{need * 1000:.0f} ms of a {budget_s * 1000:.0f} ms budget "
                           f"(raise this check's timeout_ms for inputs this long)")
        if need > left:
            raise TimeoutError(f"{what} would fit the budget, but not the time left after waiting for a worker")

    def refuse_next(self, units: float, deadline: float, what: str, run_rate: float | None = None) -> None:
        """Before each further unit of multi-unit work: running out of time partway is the input's size.
        run_rate is what this input actually costs so far: crafted text (digit runs, dense Unicode) can cost
        many times the average, and the historical estimate alone would let it run into the timeout."""
        rates = [r for r in (self.per_unit, run_rate) if r is not None]
        need = units * max(rates) if rates else 0.0
        if time.monotonic() + need > deadline - COST_MARGIN_S:
            raise Rejected(f"{what} ran out of time partway (raise this check's timeout_ms for inputs this long)")


class Detector:
    """A semantic check. Subclasses implement `_load` (heavy, blocking) and `check` (async)."""

    name: str

    def __init__(self) -> None:
        self.state = "loading"

    def load(self) -> None:
        try:
            self._load()
            self.state = "ready"
            log.info("detector %s ready", self.name)
        except Exception as exc:  # keep the service up; scans report status=error
            self.state = f"failed: {exc}"
            log.exception("detector %s failed to load", self.name)

    def _load(self) -> None:
        pass

    @property
    def ready(self) -> bool:
        return self.state == "ready"

    async def check(self, req: ScanRequest) -> CheckResult:
        raise NotImplementedError

    def skipped(self, reason: str) -> CheckResult:
        return CheckResult(check=self.name, status="skipped", details={"reason": reason})
