from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class NoiseAnalysis:
    sample_rate: int
    duration_s: float
    frequencies_hz: np.ndarray = field(repr=False)
    mean_power_db: np.ndarray = field(repr=False)
    rms: float
    spectral_flatness: float
    energy_cv: float
    energy_peak_ratio: float
    dominant_peaks_hz: tuple[float, ...]
    noise_type: str
    input_clipping: bool


@dataclass(frozen=True)
class FrequencyChoice:
    frequency_hz: float
    score: float
    local_noise_db: float
    nearest_peak_distance_hz: float


@dataclass(frozen=True)
class SelectionResult:
    choices: tuple[FrequencyChoice, ...]

    @property
    def frequencies_hz(self) -> tuple[float, ...]:
        return tuple(choice.frequency_hz for choice in self.choices)


@dataclass(frozen=True)
class ExportResult:
    output_dir: Path
    spectrum_png: Path
    noise_profile_csv: Path
    analysis_json: Path
    alarm_wav: Path


JsonDict = dict[str, Any]
