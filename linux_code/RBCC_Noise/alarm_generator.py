from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from config import AlarmConfig


def _tone_segment(
    frequencies: Sequence[float],
    duration_s: float,
    sample_rate: int,
    fade_s: float,
) -> np.ndarray:
    sample_count = max(1, round(duration_s * sample_rate))
    time = np.arange(sample_count, dtype=np.float64) / sample_rate
    carriers = np.zeros(sample_count, dtype=np.float64)
    for index, frequency in enumerate(frequencies):
        if frequency <= 0 or frequency >= sample_rate / 2:
            raise ValueError(f"frequency {frequency} Hz is outside the playable range")
        phase = index * np.pi / 7.0
        carriers += np.sin(2.0 * np.pi * float(frequency) * time + phase)
    carriers /= max(1, len(frequencies))

    fade_samples = min(round(fade_s * sample_rate), sample_count // 2)
    if fade_samples > 0:
        ramp = np.sin(np.linspace(0.0, np.pi / 2.0, fade_samples, endpoint=True)) ** 2
        carriers[:fade_samples] *= ramp
        carriers[-fade_samples:] *= ramp[::-1]
    return carriers


def generate_alarm(
    frequencies: Sequence[float],
    config: AlarmConfig | None = None,
    volume: float | None = None,
) -> np.ndarray:
    """Generate one short-short-long multi-frequency alarm cycle."""

    cfg = config or AlarmConfig()
    cfg.validate()
    selected = tuple(float(value) for value in frequencies)
    if not selected:
        raise ValueError("at least one warning frequency is required")
    output_volume = cfg.alarm_volume if volume is None else float(volume)
    if not 0 < output_volume <= 1:
        raise ValueError("volume must be within (0, 1]")

    def silence(seconds: float) -> np.ndarray:
        return np.zeros(round(seconds * cfg.sample_rate), dtype=np.float64)

    parts = [
        _tone_segment(selected, cfg.tone_short_s, cfg.sample_rate, cfg.fade_s),
        silence(cfg.gap_short_s),
        _tone_segment(selected, cfg.tone_short_s, cfg.sample_rate, cfg.fade_s),
        silence(cfg.gap_short_s),
        _tone_segment(selected, cfg.tone_long_s, cfg.sample_rate, cfg.fade_s),
        silence(cfg.gap_long_s),
    ]
    audio = np.concatenate(parts).astype(np.float64, copy=False)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / peak * output_volume
    return np.clip(audio, -output_volume, output_volume)


def _require_sounddevice():
    try:
        import sounddevice as sd
    except (ImportError, OSError) as error:
        raise RuntimeError(
            "sounddevice/PortAudio is unavailable. Install sounddevice and the "
            "platform PortAudio package, or use --no-play."
        ) from error
    return sd


def play_audio(audio: np.ndarray, sample_rate: int) -> None:
    """Play audio synchronously using the default output device."""

    sd = _require_sounddevice()
    try:
        sd.play(np.asarray(audio, dtype=np.float32), int(sample_rate), blocking=True)
    except Exception as error:  # PortAudio exceptions differ by platform.
        raise RuntimeError(f"unable to play alarm audio: {error}") from error


def save_wav(path: str | Path, audio: np.ndarray, sample_rate: int) -> Path:
    """Save floating-point audio as clipped 16-bit PCM WAV."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(audio, dtype=np.float64)
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError("audio must contain finite samples")
    pcm = np.int16(np.round(np.clip(array, -1.0, 1.0) * 32767.0))
    wavfile.write(destination, int(sample_rate), pcm)
    return destination
