from pathlib import Path

import numpy as np
from scipy.io import wavfile

from alarm_generator import generate_alarm, save_wav
from config import AlarmConfig


def test_alarm_has_short_short_long_cycle_length_and_no_clipping():
    cfg = AlarmConfig()
    audio = generate_alarm((1450.0, 2650.0, 3450.0), cfg)
    expected_seconds = (
        2 * cfg.tone_short_s
        + cfg.tone_long_s
        + 2 * cfg.gap_short_s
        + cfg.gap_long_s
    )
    assert len(audio) == round(expected_seconds * cfg.sample_rate)
    assert np.all(np.isfinite(audio))
    assert np.max(np.abs(audio)) <= cfg.alarm_volume + 1e-9
    assert np.sqrt(np.mean(audio**2)) > 0.03


def test_alarm_contains_energy_near_each_selected_frequency():
    cfg = AlarmConfig()
    selected = (1200.0, 2300.0, 3500.0)
    audio = generate_alarm(selected, cfg)
    spectrum = np.abs(np.fft.rfft(audio))
    freqs = np.fft.rfftfreq(len(audio), 1 / cfg.sample_rate)
    median = float(np.median(spectrum))
    for frequency in selected:
        index = int(np.argmin(np.abs(freqs - frequency)))
        assert spectrum[index] > median * 20


def test_save_wav_creates_readable_pcm_file(tmp_path: Path):
    cfg = AlarmConfig()
    audio = generate_alarm((1300.0, 2400.0, 3500.0), cfg)
    path = save_wav(tmp_path / "alarm.wav", audio, cfg.sample_rate)
    rate, stored = wavfile.read(path)
    assert rate == cfg.sample_rate
    assert stored.dtype == np.int16
    assert len(stored) == len(audio)
