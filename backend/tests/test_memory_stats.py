"""Process memory as the OS accounts it (footprint on macOS, RSS elsewhere)."""
import logging
import os
import sys

import pytest

from app.core.memory import stats


def test_process_memory_is_positive():
    assert stats.process_memory_bytes() > 0


def test_macos_reports_the_phys_footprint(monkeypatch):
    monkeypatch.setattr(stats.sys, "platform", "darwin")
    monkeypatch.setattr(stats, "_darwin_phys_footprint", lambda pid: 123)
    assert stats.process_memory_bytes() == 123


def test_falls_back_to_rss_when_the_footprint_is_unavailable(monkeypatch):
    monkeypatch.setattr(stats.sys, "platform", "darwin")
    monkeypatch.setattr(stats, "_darwin_phys_footprint", lambda pid: None)
    assert stats.process_memory_bytes() > 0


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_real_footprint_is_read_on_macos():
    assert stats._darwin_phys_footprint(os.getpid()) > 10 * 2**20


def test_app_info_logs_are_emitted():
    from app.main import create_app

    create_app()
    assert logging.getLogger("app").isEnabledFor(logging.INFO)
