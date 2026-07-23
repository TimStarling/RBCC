from pathlib import Path

import numpy as np
from scipy.io import wavfile

from main_cli import main


def test_file_mode_cli_runs_without_audio_hardware(tmp_path: Path):
    sr = 16000
    time = np.arange(sr, dtype=np.float64) / sr
    audio = np.int16(0.4 * np.sin(2 * np.pi * 1000 * time) * 32767)
    source = tmp_path / "factory.wav"
    wavfile.write(source, sr, audio)
    output = tmp_path / "results"

    code = main(
        [
            "--source",
            "file",
            "--input",
            str(source),
            "--no-play",
            "--output-dir",
            str(output),
        ]
    )

    assert code == 0
    assert list(output.rglob("analysis_result.json"))
    assert list(output.rglob("generated_alarm.wav"))
