from __future__ import annotations

import threading
from typing import Callable, Optional


class TokenBucket:
    """
    A thread-safe token bucket for rate-limiting resource consumption.

    The bucket has a fixed capacity. Tokens accrue at a constant ``rate``
    (tokens per second) and are added lazily on each call to ``try_consume``
    based on the time elapsed since the last refill. When tokens are requested,
    the bucket either grants them (returning ``True``) or refuses the request
    (returning ``False``), making the result suitable for direct flow control.

    The clock is injectable so tests can be fully deterministic. We deliberately
    use a callable (``time.monotonic`` by default) rather than reading the system
    clock directly inside the method so that callers retain control over time in
    tests and simulations.
    """

    def __init__(
        self,
        capacity: float,
        rate: float,
        clock: Optional[Callable[[], float]] = None,
        initial: Optional[float] = None,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if rate <= 0:
            raise ValueError("rate must be positive")
        if initial is not None:
            if initial < 0:
                raise ValueError("initial must be non-negative")
            if initial > capacity:
                raise ValueError("initial cannot exceed capacity")

        self._capacity = float(capacity)
        self._rate = float(rate)
        self._clock = clock if clock is not None else self._default_clock
        self._tokens = float(initial) if initial is not None else self._capacity
        self._last_refill = self._clock()
        self._lock = threading.Lock()

    @staticmethod
    def _default_clock() -> float:
        """
        We use ``time.monotonic`` rather than ``time.time`` because the bucket
        only needs a monotonically increasing measure of elapsed time; wall-clock
        time can jump backwards on NTP sync and corrupt the refill math.
        """
        import time
        return time.monotonic()

    @property
    def capacity(self) -> float:
        return self._capacity

    @property
    def rate(self) -> float:
        return self._rate

    def tokens(self) -> float:
        """
        Returns the current number of available tokens, refilling lazily first.
        This is approximate under concurrent consumers but never overestimates
        because tokens are capped at ``capacity``.
        """
        with self._lock:
            self._refill_locked()
            return self._tokens

    def try_consume(self, cost: float = 1.0) -> bool:
        """
        Attempt to consume ``cost`` tokens. Returns ``True`` if the request
        was granted (tokens deducted) or ``False`` if there were not enough
        tokens (no state change).

        We treat non-positive costs as always-granted rather than raising,
        because callers passing zero or negative values are expressing "no
        resource needed" and the bucket should not reject them. This matches the
        boolean flow-control contract: the caller checks the return value to
        decide whether to proceed.
        """
        if cost <= 0:
            return True
        with self._lock:
            self._refill_locked()
            if self._tokens >= cost:
                self._tokens -= cost
                return True
            return False

    def _refill_locked(self) -> None:
        """
        Internal refill that must be called while holding ``_lock``.

        We compute the elapsed time since the last refill, add the corresponding
        tokens, cap at capacity, and advance the refill timestamp. If the clock
        has not advanced (elapsed <= 0), we skip to avoid introducing a negative
        delta. Rounding to zero elapsed is harmless and avoids floating-point
        noise from repeated calls within the same clock tick.
        """
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now
