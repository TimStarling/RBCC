import pytest

from config import AlarmConfig


def test_default_config_validates():
    AlarmConfig().validate()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_rate": 0},
        {"analysis_duration": 0},
        {"min_warning_hz": 4500, "max_warning_hz": 4000},
        {"frequency_step_hz": 0},
        {"frequency_count": 0},
        {"min_frequency_spacing_hz": 100, "fallback_spacing_hz": 200},
        {"alarm_volume": 1.2},
    ],
)
def test_invalid_config_raises_value_error(kwargs):
    with pytest.raises(ValueError):
        AlarmConfig(**kwargs).validate()
