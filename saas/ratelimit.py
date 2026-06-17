# saas/ratelimit.py
# Per-tenant rate limiting.
#
# A dependency-free, in-process fixed-window counter keyed by tenant id. Each
# tenant gets its own bucket and its own per-minute allowance (driven by the
# tenant's plan, see saas.plans). This is intentionally simple and good enough
# for a single-process deployment; a multi-process deployment would swap this
# for a shared store (Redis) behind the same interface.
#
# Thread-safe via a single lock. No secrets, no I/O.

import threading
import time
from dataclasses import dataclass


@dataclass
class _Window:
    start: float       # epoch seconds when this window began
    count: int         # requests counted in the current window


class RateLimiter:
    """Fixed-window per-key rate limiter."""

    def __init__(self, window_seconds: int = 60, time_fn=time.time):
        self._window_seconds = window_seconds
        self._time_fn = time_fn
        self._lock = threading.Lock()
        self._windows = {}  # key -> _Window

    def check(self, key: str, limit_per_window: int) -> bool:
        """
        Records one request for `key` and returns True if it is within the
        allowance, False if the tenant has exceeded `limit_per_window` in the
        current window.

        A non-positive limit means "unlimited" and always returns True.
        """
        if limit_per_window is None or limit_per_window <= 0:
            return True

        now = self._time_fn()
        with self._lock:
            win = self._windows.get(key)
            if win is None or (now - win.start) >= self._window_seconds:
                # Start a fresh window.
                self._windows[key] = _Window(start=now, count=1)
                return True

            if win.count >= limit_per_window:
                return False

            win.count += 1
            return True

    def reset(self, key: str = None) -> None:
        """Clears state for one key, or all keys when key is None (tests)."""
        with self._lock:
            if key is None:
                self._windows.clear()
            else:
                self._windows.pop(key, None)
