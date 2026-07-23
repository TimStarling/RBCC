from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AlarmConfig:
    """Configuration shared by analysis, selection, synthesis, and export."""

    sample_rate: int = 16_000
    analysis_duration: float = 2.0
    stft_window_size: int = 512
    stft_hop_size: int = 256
    min_warning_hz: float = 800.0
    max_warning_hz: float = 4_000.0
    frequency_step_hz: float = 50.0
    frequency_count: int = 3
    min_frequency_spacing_hz: float = 350.0
    fallback_spacing_hz: float = 200.0
    local_bandwidth_hz: float = 90.0
    peak_exclusion_hz: float = 250.0
    peak_prominence_db: float = 8.0
    low_level_rms: float = 1e-4
    transient_energy_cv: float = 1.25
    transient_peak_ratio: float = 8.0
    broadband_flatness: float = 0.38
    tonal_flatness: float = 0.16
    alarm_volume: float = 0.35
    tone_short_s: float = 0.20
    tone_long_s: float = 0.55
    gap_short_s: float = 0.12
    gap_long_s: float = 0.30
    fade_s: float = 0.015
    output_root: Path = Path("output")

    def validate(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.analysis_duration <= 0:
            raise ValueError("analysis_duration must be positive")
        if self.stft_window_size < 32:
            raise ValueError("stft_window_size must be at least 32")
        if not 1 <= self.stft_hop_size < self.stft_window_size:
            raise ValueError("stft_hop_size must be between 1 and window_size - 1")
        if self.min_warning_hz <= 0 or self.max_warning_hz <= self.min_warning_hz:
            raise ValueError("warning frequency range is invalid")
        if self.frequency_step_hz <= 0:
            raise ValueError("frequency_step_hz must be positive")
        if self.frequency_count <= 0:
            raise ValueError("frequency_count must be positive")
        if self.fallback_spacing_hz <= 0:
            raise ValueError("fallback_spacing_hz must be positive")
        if self.min_frequency_spacing_hz < self.fallback_spacing_hz:
            raise ValueError("minimum spacing cannot be below fallback spacing")
        if self.local_bandwidth_hz <= 0 or self.peak_exclusion_hz < 0:
            raise ValueError("bandwidth and peak exclusion must be non-negative")
        if not 0 < self.alarm_volume <= 1:
            raise ValueError("alarm_volume must be within (0, 1]")
        for name in ("tone_short_s", "tone_long_s", "gap_short_s", "gap_long_s", "fade_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.tone_short_s == 0 or self.tone_long_s == 0:
            raise ValueError("tone durations must be positive")
