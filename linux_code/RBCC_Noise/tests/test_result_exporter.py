import json
from pathlib import Path

import numpy as np

from alarm_generator import generate_alarm
from config import AlarmConfig
from frequency_selector import select_warning_frequencies
from noise_analyzer import analyze_noise
from result_exporter import export_results


def test_export_results_creates_all_artifacts(tmp_path: Path):
    cfg = AlarmConfig(output_root=tmp_path)
    rng = np.random.default_rng(12)
    audio = rng.normal(0, 0.1, cfg.sample_rate)
    analysis = analyze_noise(audio, cfg.sample_rate, cfg)
    selection = select_warning_frequencies(analysis, cfg)
    alarm = generate_alarm(selection.frequencies_hz, cfg)

    result = export_results(
        analysis,
        selection,
        alarm,
        cfg,
        processing_ms=18.5,
        output_root=tmp_path,
        timestamp="2026-07-17_220500",
    )

    assert result.spectrum_png.is_file()
    assert result.noise_profile_csv.is_file()
    assert result.analysis_json.is_file()
    assert result.alarm_wav.is_file()
    payload = json.loads(result.analysis_json.read_text(encoding="utf-8"))
    assert payload["noise_type"] == analysis.noise_type
    assert payload["best_warning_frequencies_hz"] == list(selection.frequencies_hz)
    assert payload["processing_ms"] == 18.5
    assert len(payload["frequency_choices"]) == 3
