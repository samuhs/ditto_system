"""Travamento watchdog: pauses a running experiment that stops making progress.

One `StallWatchdog` per running experiment (created in `_run_experiment`).
`heartbeat()` renews its deadline; a result recorded, a phase change, or a
Combinação starting all call it. If `limit_s` passes without a heartbeat,
`on_stall` fires exactly once, on the watchdog's own thread, never the loop's:
the whole point is that the loop thread may be stuck inside a call and unable
to notice anything on its own (ADR 0001, "threads presas são abandonadas").
"""
import threading
import time
from collections.abc import Callable

# How often the watchdog thread rechecks its deadline. Small relative to the
# fractions-of-a-second limits the test suite injects, negligible next to the
# minutes-long default.
_POLL_S = 0.02


class StallWatchdog:
    """Fires `on_stall` once, `limit_s` seconds after the last `heartbeat()`."""

    def __init__(self, limit_s: float, on_stall: Callable[[], None]) -> None:
        self._limit_s = limit_s
        self._on_stall = on_stall
        self._lock = threading.Lock()
        self._deadline = time.monotonic() + limit_s
        self._stopped = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "StallWatchdog":
        """Start watching; returns self so callers can do `watchdog = StallWatchdog(...).start()`."""
        self._thread.start()
        return self

    def heartbeat(self) -> None:
        """Renew the deadline: the run just made progress."""
        with self._lock:
            if not self._stopped:
                self._deadline = time.monotonic() + self._limit_s

    def stop(self) -> None:
        """Stop watching for good (the run ended on its own). Safe to call more than once."""
        with self._lock:
            self._stopped = True
        # The watchdog thread never blocks (it only sleeps in short slices), so a
        # short join is enough; it is a daemon thread regardless, never holding
        # process exit hostage.
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while True:
            with self._lock:
                if self._stopped:
                    return
                remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                with self._lock:
                    if self._stopped:
                        return
                    self._stopped = True  # fire at most once
                self._on_stall()
                return
            time.sleep(min(remaining, _POLL_S))
