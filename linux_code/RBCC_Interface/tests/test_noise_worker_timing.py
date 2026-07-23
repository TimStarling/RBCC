from __future__ import annotations

import sys
from pathlib import Path

import pytest


INTERFACE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTERFACE_DIR))

import noise_worker  # noqa: E402


def test_capture_and_update_constants() -> None:
    assert noise_worker.CAPTURE_DURATION_SECONDS == pytest.approx(0.8)
    assert noise_worker.UPDATE_INTERVAL_SECONDS == pytest.approx(4.5)


def test_remaining_cycle_seconds_uses_period_remainder() -> None:
    remaining = noise_worker.remaining_cycle_seconds(10.0, now=10.8)
    assert remaining == pytest.approx(3.7)


def test_remaining_cycle_seconds_never_returns_negative() -> None:
    remaining = noise_worker.remaining_cycle_seconds(10.0, now=14.7)
    assert remaining == 0.0


def test_dashboard_copy_matches_capture_duration() -> None:
    source = (INTERFACE_DIR / "main.py").read_text(encoding="utf-8")
    assert "正在采集 0.8 秒音频…" in source
    assert "正在采集 2 秒音频…" not in source


def test_alarm_config_selects_one_four_digit_frequency() -> None:
    config = noise_worker.build_alarm_config()
    assert config.analysis_duration == pytest.approx(0.8)
    assert config.min_warning_hz == pytest.approx(2000.0)
    assert config.max_warning_hz == pytest.approx(5000.0)
    assert config.frequency_count == 1
