import numpy as np

from config import AlarmConfig
from frequency_selector import select_warning_frequencies
from noise_analyzer import analyze_noise


def sine(freq: float, sr: int, seconds: float = 2.0, amplitude: float = 0.8) -> np.ndarray:
    t = np.arange(int(sr * seconds), dtype=np.float64) / sr
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_strong_1000_hz_tone_is_avoided():
    cfg = AlarmConfig()
    analysis = analyze_noise(sine(1000, cfg.sample_rate), cfg.sample_rate, cfg)
    result = select_warning_frequencies(analysis, cfg)
    assert len(result.choices) == 3
    assert all(abs(freq - 1000) >= cfg.peak_exclusion_hz for freq in result.frequencies_hz)


def test_multiple_dominant_peaks_are_avoided():
    cfg = AlarmConfig()
    audio = (
        sine(1000, cfg.sample_rate, amplitude=0.7)
        + sine(1800, cfg.sample_rate, amplitude=0.6)
        + sine(2800, cfg.sample_rate, amplitude=0.5)
    ) / 3
    analysis = analyze_noise(audio, cfg.sample_rate, cfg)
    result = select_warning_frequencies(analysis, cfg)
    for selected in result.frequencies_hz:
        assert all(abs(selected - peak) >= cfg.peak_exclusion_hz for peak in analysis.dominant_peaks_hz[:3])


def test_selected_frequencies_have_required_spacing():
    cfg = AlarmConfig()
    rng = np.random.default_rng(4)
    audio = rng.normal(0, 0.2, cfg.sample_rate * 2)
    analysis = analyze_noise(audio, cfg.sample_rate, cfg)
    result = select_warning_frequencies(analysis, cfg)
    frequencies = sorted(result.frequencies_hz)
    assert len(frequencies) == cfg.frequency_count
    assert min(np.diff(frequencies)) >= cfg.min_frequency_spacing_hz


def test_selection_is_deterministic_for_same_input():
    cfg = AlarmConfig()
    analysis = analyze_noise(sine(1450, cfg.sample_rate), cfg.sample_rate, cfg)
    first = select_warning_frequencies(analysis, cfg)
    second = select_warning_frequencies(analysis, cfg)
    assert first.frequencies_hz == second.frequencies_hz


def test_previous_frequencies_add_stability_without_breaking_spacing():
    cfg = AlarmConfig()
    rng = np.random.default_rng(8)
    analysis = analyze_noise(rng.normal(0, 0.15, cfg.sample_rate * 2), cfg.sample_rate, cfg)
    baseline = select_warning_frequencies(analysis, cfg)
    stable = select_warning_frequencies(analysis, cfg, previous_frequencies=baseline.frequencies_hz)
    assert stable.frequencies_hz == baseline.frequencies_hz
