from __future__ import annotations

import math

import numpy as np
from scipy import signal

from config import AlarmConfig
from models import NoiseAnalysis

_EPS = np.finfo(np.float64).tiny


def _to_mono_float(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio)
    if array.size == 0:
        raise ValueError("audio input is empty")
    if array.ndim == 1:
        mono = array
    elif array.ndim == 2:
        mono = np.mean(array, axis=1)
    else:
        raise ValueError("audio must be one-dimensional or shaped as samples x channels")
    mono = np.asarray(mono, dtype=np.float64)
    if not np.all(np.isfinite(mono)):
        raise ValueError("audio contains NaN or infinite samples")
    return mono


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if source_rate == target_rate:
        return audio
    divisor = math.gcd(source_rate, target_rate)
    up = target_rate // divisor
    down = source_rate // divisor
    return signal.resample_poly(audio, up, down).astype(np.float64, copy=False)


def _frame_energy(audio: np.ndarray, frame_size: int, hop_size: int) -> np.ndarray:
    if len(audio) < frame_size:
        audio = np.pad(audio, (0, frame_size - len(audio)))
    starts = np.arange(0, len(audio) - frame_size + 1, hop_size, dtype=int)
    if starts.size == 0:
        starts = np.array([0])
    return np.asarray(
        [np.mean(np.square(audio[start : start + frame_size])) for start in starts],
        dtype=np.float64,
    )


def analyze_noise(
    audio: np.ndarray,
    sample_rate: int,
    config: AlarmConfig | None = None,
) -> NoiseAnalysis:
    """Analyze factory noise and return time-frequency features.

    The input can be mono or ``samples x channels``. It is converted to the
    configured sampling rate so the downstream frequency selector always sees
    a consistent spectrum.
    """

    cfg = config or AlarmConfig()
    cfg.validate()
    mono = _to_mono_float(audio)
    mono = _resample(mono, int(sample_rate), cfg.sample_rate)

    input_clipping = bool(np.max(np.abs(mono)) >= 0.999)
    duration_s = len(mono) / cfg.sample_rate
    rms = float(np.sqrt(np.mean(np.square(mono))))

    window_size = cfg.stft_window_size
    if len(mono) < window_size:
        mono_for_stft = np.pad(mono, (0, window_size - len(mono)))
    else:
        mono_for_stft = mono

    frequencies, _, spectrum = signal.stft(
        mono_for_stft,
        fs=cfg.sample_rate,
        window="hann",
        nperseg=window_size,
        noverlap=window_size - cfg.stft_hop_size,
        nfft=window_size,
        detrend=False,
        return_onesided=True,
        boundary=None,
        padded=False,
    )
    power = np.square(np.abs(spectrum))
    mean_power = np.mean(power, axis=1) if power.ndim == 2 else power
    mean_power_db = 10.0 * np.log10(np.maximum(mean_power, _EPS))

    energy = _frame_energy(mono, window_size, cfg.stft_hop_size)
    energy_mean = float(np.mean(energy))
    energy_cv = float(np.std(energy) / (energy_mean + _EPS))
    positive_energy = energy[energy > _EPS]
    median_energy = float(np.median(positive_energy)) if positive_energy.size else 0.0
    energy_peak_ratio = float(np.max(energy) / (median_energy + _EPS)) if energy.size else 0.0

    analysis_band = (frequencies >= 80.0) & (
        frequencies <= min(float(cfg.sample_rate) / 2.0 - 1.0, 6_000.0)
    )
    band_power = mean_power[analysis_band]
    if band_power.size and np.mean(band_power) > _EPS:
        spectral_flatness = float(
            np.exp(np.mean(np.log(np.maximum(band_power, _EPS))))
            / np.mean(np.maximum(band_power, _EPS))
        )
    else:
        spectral_flatness = 0.0

    band_db = mean_power_db[analysis_band]
    band_freqs = frequencies[analysis_band]
    if band_db.size >= 3:
        peak_indices, properties = signal.find_peaks(
            band_db,
            prominence=cfg.peak_prominence_db,
            distance=max(1, int(100.0 / (frequencies[1] - frequencies[0]))),
        )
        prominences = properties.get("prominences", np.zeros_like(peak_indices, dtype=float))
        if peak_indices.size:
            ranking = sorted(
                range(peak_indices.size),
                key=lambda index: (prominences[index], band_db[peak_indices[index]]),
                reverse=True,
            )[:8]
            dominant_peaks_hz = tuple(
                float(band_freqs[peak_indices[index]]) for index in ranking
            )
        else:
            dominant_peaks_hz = ()
    else:
        dominant_peaks_hz = ()

    if rms < cfg.low_level_rms:
        noise_type = "low_level"
    elif energy_cv >= cfg.transient_energy_cv or energy_peak_ratio >= cfg.transient_peak_ratio:
        noise_type = "transient"
    elif dominant_peaks_hz and spectral_flatness <= cfg.tonal_flatness:
        noise_type = "tonal"
    elif spectral_flatness >= cfg.broadband_flatness:
        noise_type = "broadband_mixed"
    else:
        noise_type = "steady_background"

    return NoiseAnalysis(
        sample_rate=cfg.sample_rate,
        duration_s=float(duration_s),
        frequencies_hz=np.asarray(frequencies, dtype=np.float64),
        mean_power_db=np.asarray(mean_power_db, dtype=np.float64),
        rms=rms,
        spectral_flatness=spectral_flatness,
        energy_cv=energy_cv,
        energy_peak_ratio=energy_peak_ratio,
        dominant_peaks_hz=dominant_peaks_hz,
        noise_type=noise_type,
        input_clipping=input_clipping,
    )
