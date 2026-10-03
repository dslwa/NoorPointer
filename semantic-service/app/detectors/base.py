import logging

from app.schemas import CheckResult, ScanRequest

log = logging.getLogger(__name__)


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
