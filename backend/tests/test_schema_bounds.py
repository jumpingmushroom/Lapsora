"""Validation-bound regressions (F-36): nonsense config must be rejected."""

import pytest
from pydantic import ValidationError

from app.schemas import HealthConfig, PrusaLinkConfig, TimelapseGenerate, TimelapseScheduleUpdate


def test_prusalink_rejects_inverted_interval_bounds():
    with pytest.raises(ValidationError):
        PrusaLinkConfig(base_url="http://x", min_interval_seconds=100, max_interval_seconds=10)
    # valid ordering still accepted
    PrusaLinkConfig(base_url="http://x", min_interval_seconds=2, max_interval_seconds=120)


def test_health_config_rejects_zero_threshold_and_bad_percent():
    with pytest.raises(ValidationError):
        HealthConfig(failure_threshold=0)
    with pytest.raises(ValidationError):
        HealthConfig(low_disk_threshold_percent=0)
    with pytest.raises(ValidationError):
        HealthConfig(low_disk_threshold_percent=100)


def test_generate_rejects_unknown_format():
    with pytest.raises(ValidationError):
        TimelapseGenerate(format="mp4/../x")
    TimelapseGenerate(format="webm")  # allowed


def test_schedule_update_rejects_negative_lookback():
    with pytest.raises(ValidationError):
        TimelapseScheduleUpdate(lookback_hours=-5)
