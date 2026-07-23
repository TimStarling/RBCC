from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from config import AlarmConfig
from models import FrequencyChoice, NoiseAnalysis, SelectionResult


def _normalise(values: np.ndarray, invert: bool = False) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    low = float(np.min(values))
    high = float(np.max(values))
    if high - low < 1e-12:
        result = np.ones_like(values)
    else:
        result = (values - low) / (high - low)
    return 1.0 - result if invert else result


def _local_noise_db(analysis: NoiseAnalysis, frequency_hz: float, bandwidth_hz: float) -> float:
    frequencies = analysis.frequencies_hz
    spectrum = analysis.mean_power_db
    mask = np.abs(frequencies - frequency_hz) <= bandwidth_hz
    if np.any(mask):
        return float(np.mean(spectrum[mask]))
    return float(np.interp(frequency_hz, frequencies, spectrum))


def _nearest_peak_distance(frequency_hz: float, peaks: tuple[float, ...]) -> float:
    if not peaks:
        return float("inf")
    return float(min(abs(frequency_hz - peak) for peak in peaks))


def select_warning_frequencies(
    analysis: NoiseAnalysis,
    config: AlarmConfig | None = None,
    previous_frequencies: Sequence[float] | None = None,
) -> SelectionResult:
    """Score and choose warning carriers that avoid measured factory noise."""

    cfg = config or AlarmConfig(sample_rate=analysis.sample_rate)
    cfg.validate()
    nyquist_guard = analysis.sample_rate * 0.45
    maximum = min(cfg.max_warning_hz, nyquist_guard)
    if maximum <= cfg.min_warning_hz:
        raise ValueError("sample rate is too low for the configured warning frequency range")

    candidates = np.arange(
        cfg.min_warning_hz,
        maximum + cfg.frequency_step_hz * 0.5,
        cfg.frequency_step_hz,
        dtype=np.float64,
    )
    if candidates.size < cfg.frequency_count:
        raise ValueError("not enough candidate frequencies")

    local_noise = np.asarray(
        [_local_noise_db(analysis, frequency, cfg.local_bandwidth_hz) for frequency in candidates]
    )
    energy_score = _normalise(local_noise, invert=True)

    peak_distances = np.asarray(
        [_nearest_peak_distance(frequency, analysis.dominant_peaks_hz) for frequency in candidates],
        dtype=np.float64,
    )
    if analysis.dominant_peaks_hz:
        finite_distance = np.minimum(peak_distances, cfg.peak_exclusion_hz * 4.0)
        peak_score = np.clip(finite_distance / (cfg.peak_exclusion_hz * 2.0), 0.0, 1.0)
    else:
        peak_score = np.ones_like(candidates)

    # The middle speech-sensitive band is preferred, but it is a soft term only.
    hearing_score = np.exp(-0.5 * np.square((candidates - 2_400.0) / 1_150.0))

    if previous_frequencies:
        previous = np.asarray(tuple(previous_frequencies), dtype=np.float64)
        distance_to_previous = np.min(np.abs(candidates[:, None] - previous[None, :]), axis=1)
        stability_score = np.exp(-0.5 * np.square(distance_to_previous / 120.0))
    else:
        stability_score = np.zeros_like(candidates)

    scores = (
        0.55 * energy_score
        + 0.25 * peak_score
        + 0.10 * hearing_score
        + 0.10 * stability_score
    )

    hard_exclusion = np.zeros(candidates.shape, dtype=bool)
    if analysis.noise_type in {"tonal", "steady_background"} and analysis.dominant_peaks_hz:
        hard_exclusion = peak_distances < cfg.peak_exclusion_hz
        scores = scores.copy()
        scores[hard_exclusion] = -np.inf

    order = sorted(
        range(candidates.size),
        key=lambda index: (scores[index], -abs(candidates[index] - 2_400.0), -candidates[index]),
        reverse=True,
    )

    def choose_with_spacing(spacing: float, allow_excluded: bool = False) -> list[int]:
        chosen: list[int] = []
        for index in order:
            if not np.isfinite(scores[index]) and not allow_excluded:
                continue
            frequency = candidates[index]
            if all(abs(frequency - candidates[other]) >= spacing for other in chosen):
                chosen.append(index)
                if len(chosen) == cfg.frequency_count:
                    break
        return chosen

    chosen_indices = choose_with_spacing(cfg.min_frequency_spacing_hz)
    if len(chosen_indices) < cfg.frequency_count:
        chosen_indices = choose_with_spacing(cfg.fallback_spacing_hz)
    if len(chosen_indices) < cfg.frequency_count:
        # Last-resort behavior is used only when the configured range is very crowded.
        chosen_indices = choose_with_spacing(cfg.fallback_spacing_hz, allow_excluded=True)
    if len(chosen_indices) < cfg.frequency_count:
        raise RuntimeError("unable to choose enough separated warning frequencies")

    choices = tuple(
        FrequencyChoice(
            frequency_hz=float(candidates[index]),
            score=float(scores[index]) if np.isfinite(scores[index]) else 0.0,
            local_noise_db=float(local_noise[index]),
            nearest_peak_distance_hz=float(peak_distances[index]),
        )
        for index in chosen_indices
    )
    return SelectionResult(choices=choices)
