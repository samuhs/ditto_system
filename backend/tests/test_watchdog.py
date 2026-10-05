"""Unit tests for StallWatchdog (Travamento, #20), isolated from the orchestrator.

The orchestrator's own Travamento tests (test_orchestrator.py) only exercise a
watchdog whose very first heartbeat happens right after construction, so they
never notice whether a *later* heartbeat actually renews the deadline. These
tests cover that directly, against the class itself.
"""
import threading
import time

from app.experiments.watchdog import StallWatchdog


def test_fires_once_after_the_limit_with_no_heartbeat():
    """With nothing renewing the deadline, on_stall fires once the limit passes."""
    fired = threading.Event()
    watchdog = StallWatchdog(0.05, fired.set).start()
    try:
        assert fired.wait(1.0), "on_stall should have fired by now"
    finally:
        watchdog.stop()


def test_heartbeat_keeps_deferring_the_stall():
    """Repeated heartbeats must keep pushing the deadline forward.

    Without this, a watchdog that renews its deadline only once (at creation)
    would fire on any experiment that simply runs longer than the Travamento
    limit, regardless of how much progress it is making.
    """
    fired = threading.Event()
    watchdog = StallWatchdog(0.05, fired.set).start()
    try:
        deadline = time.monotonic() + 0.3  # well past the original 0.05s limit
        while time.monotonic() < deadline:
            watchdog.heartbeat()
            time.sleep(0.01)
        assert not fired.is_set(), "heartbeats should have kept the watchdog from firing"
    finally:
        watchdog.stop()


def test_stop_prevents_a_later_fire():
    """Once stopped, the watchdog must never call on_stall, even past its deadline."""
    fired = threading.Event()
    watchdog = StallWatchdog(0.05, fired.set).start()
    watchdog.stop()
    time.sleep(0.1)
    assert not fired.is_set(), "a stopped watchdog must never fire"
