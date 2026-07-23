from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from alarm_generator import save_wav
from config import AlarmConfig
from models import ExportResult, NoiseAnalysis, SelectionResult


def _serialisable_config(config: AlarmConfig) -> dict[str, object]:
    payload = asdict(config)
    payload["output_root"] = str(payload["output_root"])
    return payload


def export_results(
    analysis: NoiseAnalysis,
    selection: SelectionResult,
    alarm_audio: np.ndarray,
    config: AlarmConfig,
    processing_ms: float,
    output_root: str | Path | None = None,
    timestamp: str | None = None,
) -> ExportResult:
    """Export spectrum plot, CSV profile, JSON summary, and WAV alarm."""

    root = Path(output_root) if output_root is not None else Path(config.output_root)
    stamp = timestamp or datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = root / stamp
    counter = 1
    while output_dir.exists() and timestamp is None:
        output_dir = root / f"{stamp}_{counter:02d}"
        counter += 1
    output_dir.mkdir(parents=True, exist_ok=True)

    spectrum_png = output_dir / "spectrum.png"
    noise_profile_csv = output_dir / "noise_profile.csv"
    analysis_json = output_dir / "analysis_result.json"
    alarm_wav = output_dir / "generated_alarm.wav"

    figure, axis = plt.subplots(figsize=(11, 5.5))
    valid = analysis.frequencies_hz <= min(config.max_warning_hz + 1000, analysis.sample_rate / 2)
    axis.plot(analysis.frequencies_hz[valid], analysis.mean_power_db[valid], linewidth=1.2)
    for choice in selection.choices:
        axis.axvline(choice.frequency_hz, linestyle="--", linewidth=1.1)
        axis.text(
            choice.frequency_hz,
            float(np.max(analysis.mean_power_db[valid])) if np.any(valid) else 0.0,
            f" {choice.frequency_hz:.0f} Hz",
            rotation=90,
            va="top",
            fontsize=8,
        )
    axis.set_title(f"Factory Noise Spectrum — {analysis.noise_type}")
    axis.set_xlabel("Frequency (Hz)")
    axis.set_ylabel("Mean power (dB)")
    axis.grid(True, alpha=0.25)
    figure.tight_layout()
    figure.savefig(spectrum_png, dpi=220)
    plt.close(figure)

    with noise_profile_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_hz", "mean_power_db"])
        writer.writerows(
            (f"{frequency:.6f}", f"{power:.6f}")
            for frequency, power in zip(analysis.frequencies_hz, analysis.mean_power_db, strict=True)
        )

    payload = {
        "noise_type": analysis.noise_type,
        "sample_rate": analysis.sample_rate,
        "duration_s": analysis.duration_s,
        "rms": analysis.rms,
        "spectral_flatness": analysis.spectral_flatness,
        "energy_cv": analysis.energy_cv,
        "energy_peak_ratio": analysis.energy_peak_ratio,
        "dominant_noise_peaks_hz": list(analysis.dominant_peaks_hz),
        "input_clipping": analysis.input_clipping,
        "best_warning_frequencies_hz": list(selection.frequencies_hz),
        "frequency_choices": [
            {
                "frequency_hz": choice.frequency_hz,
                "score": choice.score,
                "local_noise_db": choice.local_noise_db,
                "nearest_peak_distance_hz": choice.nearest_peak_distance_hz,
            }
            for choice in selection.choices
        ],
        "processing_ms": float(processing_ms),
        "config": _serialisable_config(config),
    }
    analysis_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_wav(alarm_wav, alarm_audio, config.sample_rate)

    return ExportResult(
        output_dir=output_dir,
        spectrum_png=spectrum_png,
        noise_profile_csv=noise_profile_csv,
        analysis_json=analysis_json,
        alarm_wav=alarm_wav,
    )
