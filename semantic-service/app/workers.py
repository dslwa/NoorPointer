import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor


class Overloaded(Exception):
    """No worker became free within the wait limit."""


class Reservation:
    """A held worker slot. Submitting hands the slot to the job, which releases it when it finishes;
    if nothing is submitted, leaving the `async with` block releases it."""

    def __init__(self, workers: "BoundedWorkers") -> None:
        self._workers = workers
        self.submitted = False

    def submit(self, fn, *args) -> asyncio.Future:
        if self.submitted:
            raise RuntimeError("a reservation runs one job")
        # run_in_executor submits synchronously, so the job is guaranteed to run even if the awaiting
        # coroutine is cancelled right after this call.
        future = asyncio.get_running_loop().run_in_executor(self._workers._pool, fn, *args)
        self.submitted = True
        # The slot is freed when the thread is really done, not when the caller stops waiting.
        future.add_done_callback(lambda _: self._workers._slots.release())
        # shield: a caller that stops waiting must not cancel the job itself
        return asyncio.shield(future)


class BoundedWorkers:
    """A dedicated thread pool whose slots stay taken until the blocking work really finishes.

    asyncio.wait_for only cancels the awaiting coroutine: a thread keeps running after a timeout. With
    the shared default pool, one big request could pile up unbounded background work. Here a slot is
    held for the whole lifetime of the thread's work, so at most `size` jobs ever run. Callers wait for
    a slot in FIFO order (cancellable, e.g. by their check timeout) instead of queueing more threads.
    """

    def __init__(self, name: str, size: int) -> None:
        self.size = size
        self._slots = asyncio.Semaphore(size)  # only touched from the event loop (done-callbacks run there)
        self._pool = ThreadPoolExecutor(max_workers=size, thread_name_prefix=name)
        self.name = name

    @contextlib.asynccontextmanager
    async def reserve(self, wait_s: float | None = None):
        """Wait for a slot (forever, or up to wait_s, then Overloaded)."""
        try:
            if wait_s is None:
                await self._slots.acquire()
            else:
                await asyncio.wait_for(self._slots.acquire(), max(wait_s, 0))
        except TimeoutError as exc:
            raise Overloaded(f"no {self.name} worker free within {wait_s:.1f}s") from exc
        reservation = Reservation(self)
        try:
            yield reservation
        finally:
            if not reservation.submitted:
                self._slots.release()

    async def run(self, fn, *args):
        async with self.reserve() as reservation:
            future = reservation.submit(fn, *args)
        return await future

    def shutdown(self) -> None:
        """Stop accepting work; running jobs finish in the background (never block app shutdown on them)."""
        self._pool.shutdown(wait=False, cancel_futures=True)
