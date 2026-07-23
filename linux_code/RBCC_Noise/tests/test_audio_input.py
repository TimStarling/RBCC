from pathlib import Path

import numpy as np
from scipy.io import wavfile

from audio_input import load_wav


def test_load_wav_converts_stereo_to_mono_and_resamples(tmp_path: Path):
    source_rate = 8000
    target_rate = 16000
    t = np.arange(source_rate, dtype=np.float64) / source_rate
    left = 0.5 * np.sin(2 * np.pi * 1000 * t)
    right = 0.25 * np.sin(2 * np.pi * 1000 * t)
    stereo = np.column_stack([left, right])
    pcm = np.int16(np.clip(stereo, -1, 1) * 32767)
    source = tmp_path / "stereo.wav"
    wavfile.write(source, source_rate, pcm)

    audio, sample_rate = load_wav(source, target_rate)

    assert sample_rate == target_rate
    assert audio.ndim == 1
    assert len(audio) == target_rate
    assert np.max(np.abs(audio)) <= 1.0
    assert np.sqrt(np.mean(audio**2)) > 0.1


def test_load_wav_rejects_empty_file(tmp_path: Path):
    source = tmp_path / "empty.wav"
    wavfile.write(source, 16000, np.array([], dtype=np.int16))
    try:
        load_wav(source, 16000)
    except ValueError as error:
        assert "empty" in str(error).lower()
    else:
        raise AssertionError("empty WAV should be rejected")
