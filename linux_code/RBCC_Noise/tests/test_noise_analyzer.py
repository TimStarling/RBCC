import numpy as np

from config import AlarmConfig
from noise_analyzer import analyze_noise


def sine(freq: float, seconds: float = 2.0, sr: int = 16_000, amplitude: float = 0.7) -> np.ndarray:
    t = np.arange(int(seconds * sr), dtype=np.float64) / sr
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_low_level_input_is_classified_and_spectrum_is_finite():
    cfg = AlarmConfig()
    result = analyze_noise(np.zeros(cfg.sample_rate), cfg.sample_rate, cfg)
    assert result.noise_type == "low_level"
    assert result.rms == 0.0
    assert np.all(np.isfinite(result.mean_power_db))


def test_tonal_signal_detects_1000_hz_peak():
    cfg = AlarmConfig()
    result = analyze_noise(sine(1000), cfg.sample_rate, cfg)
    assert result.noise_type == "tonal"
    assert any(abs(peak - 1000) <= 40 for peak in result.dominant_peaks_hz)
    assert result.spectral_flatness < cfg.tonal_flatness


def test_transient_impulses_are_classified_as_transient():
    cfg = AlarmConfig()
    audio = np.zeros(cfg.sample_rate * 2, dtype=np.float64)
    audio[2000:2010] = 0.9
    audio[14000:14010] = -0.9
    result = analyze_noise(audio, cfg.sample_rate, cfg)
    assert result.noise_type == "transient"
    assert result.energy_peak_ratio >= cfg.transient_peak_ratio or result.energy_cv >= cfg.transient_energy_cv


def test_clipping_is_reported():
    cfg = AlarmConfig()
    audio = sine(1400, amplitude=1.0)
    result = analyze_noise(audio, cfg.sample_rate, cfg)
    assert result.input_clipping is True


def test_stereo_input_is_converted_to_mono():
    cfg = AlarmConfig()
    mono = sine(1200)
    stereo = np.column_stack([mono, mono])
    result = analyze_noise(stereo, cfg.sample_rate, cfg)
    assert result.duration_s == 2.0
    assert any(abs(peak - 1200) <= 40 for peak in result.dominant_peaks_hz)
