#!/usr/bin/env python3
"""Capture, persist, and analyze 0.8-second noise samples every 4.5 seconds."""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np


NOISE_PROJECT_DIR = Path("/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise")
CAPTURE_DURATION_SECONDS = 0.8
UPDATE_INTERVAL_SECONDS = 4.5
BLUETOOTH_CARD = "bluez_card.28_2D_7F_E7_2F_8F"
BLUETOOTH_PROFILE = "handsfree_head_unit"
AUDIO_DIR = Path(__file__).resolve().parent / "runtime" / "environment_audio"
ENVIRONMENT_WAV = AUDIO_DIR / "latest.wav"
sys.path.insert(0, str(NOISE_PROJECT_DIR))

from alarm_generator import save_wav  # noqa: E402
from audio_input import load_wav  # noqa: E402
from config import AlarmConfig  # noqa: E402
from frequency_selector import select_warning_frequencies  # noqa: E402
from noise_analyzer import analyze_noise  # noqa: E402


stop_event = threading.Event()


def emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def remaining_cycle_seconds(cycle_started: float, now: float | None = None) -> float:
    """Return the interruptible wait needed to preserve the fixed cadence."""
    current = time.monotonic() if now is None else now
    elapsed = current - cycle_started
    return max(0.0, UPDATE_INTERVAL_SECONDS - elapsed)


def strongest_noise_frequency(analysis) -> float:
    """Return the strongest measured frequency in the 80-6000 Hz analysis band."""
    upper = min(6000.0, analysis.sample_rate / 2.0 - 1.0)
    valid = (analysis.frequencies_hz >= 80.0) & (analysis.frequencies_hz <= upper)
    if not np.any(valid):
        raise RuntimeError("频谱中没有有效频点")
    frequencies = analysis.frequencies_hz[valid]
    powers = analysis.mean_power_db[valid]
    return float(frequencies[int(np.argmax(powers))])


def build_alarm_config() -> AlarmConfig:
    """Build the automatic single-frequency selection configuration."""
    return AlarmConfig(
        sample_rate=16000,
        analysis_duration=CAPTURE_DURATION_SECONDS,
        min_warning_hz=2000.0,
        max_warning_hz=5000.0,
        frequency_count=1,
    )


def run_command(*command: str, timeout: float) -> str:
    """Run one local audio command and return stdout or raise a useful error."""
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"命令执行失败 {' '.join(command)}: {detail}")
    return result.stdout.strip()


def prepare_airpods_hfp() -> str:
    """Enable the AirPods microphone profile and return its PulseAudio source."""
    run_command(
        "pactl",
        "set-card-profile",
        BLUETOOTH_CARD,
        BLUETOOTH_PROFILE,
        timeout=8.0,
    )
    listing = run_command("pactl", "list", "short", "sources", timeout=5.0)
    for line in listing.splitlines():
        columns = line.split("\t")
        if len(columns) >= 2 and columns[1].startswith("bluez_source."):
            return columns[1]
    raise RuntimeError("AirPods HFP 麦克风输入源不存在")


def record_environment_audio(source: str, config: AlarmConfig) -> Path:
    """Record and publish an exact 0.8-second, 16 kHz mono WAV."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    temporary = AUDIO_DIR / "latest.tmp.wav"
    run_command(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "pulse",
        "-i",
        source,
        "-t",
        f"{CAPTURE_DURATION_SECONDS:.3f}",
        "-ac",
        "1",
        "-ar",
        str(config.sample_rate),
        "-c:a",
        "pcm_s16le",
        str(temporary),
        timeout=6.0,
    )
    if not temporary.is_file() or temporary.stat().st_size <= 44:
        raise RuntimeError("环境音频文件为空")

    recorded, sample_rate = load_wav(temporary, config.sample_rate)
    required_samples = round(CAPTURE_DURATION_SECONDS * sample_rate)
    if recorded.size < required_samples:
        recorded = np.pad(recorded, (0, required_samples - recorded.size))
    else:
        recorded = recorded[-required_samples:]
    save_wav(ENVIRONMENT_WAV, recorded, sample_rate)
    temporary.unlink(missing_ok=True)
    return ENVIRONMENT_WAV


def main() -> int:
    signal.signal(signal.SIGTERM, lambda *_args: stop_event.set())
    signal.signal(signal.SIGINT, lambda *_args: stop_event.set())
    config = build_alarm_config()
    previous: tuple[float, ...] | None = None

    while not stop_event.is_set():
        cycle_started = time.monotonic()
        try:
            source = prepare_airpods_hfp()
            recording = record_environment_audio(source, config)
            if stop_event.is_set():
                break

            audio, sample_rate = load_wav(recording, config.sample_rate)
            required_samples = round(config.analysis_duration * sample_rate)
            audio = audio[-required_samples:]
            if audio.size < required_samples:
                raise RuntimeError("环境音频不足 0.8 秒")

            analysis = analyze_noise(audio, sample_rate, config)
            selection = select_warning_frequencies(analysis, config, previous)
            previous = selection.frequencies_hz
            emit(
                {
                    "status": "ok",
                    "max_noise_hz": strongest_noise_frequency(analysis),
                    "best_alarm_hz": float(selection.choices[0].frequency_hz),
                    "noise_type": analysis.noise_type,
                    "device": source,
                    "recording_path": str(recording),
                    "captured_at": time.time(),
                }
            )
        except Exception as error:
            emit({"status": "no_input", "message": str(error), "captured_at": time.time()})

        stop_event.wait(remaining_cycle_seconds(cycle_started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
