from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal
from scipy.io import wavfile


def _require_sounddevice():
    try:
        import sounddevice as sd
    except (ImportError, OSError) as error:
        raise RuntimeError(
            "Microphone access requires sounddevice and PortAudio. "
            "On Raspberry Pi OS install libportaudio2/portaudio19-dev first."
        ) from error
    return sd


def _pcm_to_float(data: np.ndarray) -> np.ndarray:
    if np.issubdtype(data.dtype, np.floating):
        return np.asarray(data, dtype=np.float64)
    if data.dtype == np.uint8:
        return (np.asarray(data, dtype=np.float64) - 128.0) / 128.0
    if np.issubdtype(data.dtype, np.integer):
        info = np.iinfo(data.dtype)
        scale = float(max(abs(info.min), info.max))
        return np.asarray(data, dtype=np.float64) / scale
    raise ValueError(f"unsupported WAV sample type: {data.dtype}")


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return audio
    divisor = math.gcd(int(source_rate), int(target_rate))
    return signal.resample_poly(
        audio,
        int(target_rate) // divisor,
        int(source_rate) // divisor,
    ).astype(np.float64, copy=False)


def load_wav(path: str | Path, target_sample_rate: int) -> tuple[np.ndarray, int]:
    """Load a WAV file, convert it to mono float64, and resample it."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"WAV file not found: {source}")
    try:
        source_rate, raw = wavfile.read(source)
    except Exception as error:
        raise ValueError(f"unable to read WAV file: {error}") from error
    if raw.size == 0:
        raise ValueError("WAV file is empty")
    if source_rate <= 0 or target_sample_rate <= 0:
        raise ValueError("sample rates must be positive")
    audio = _pcm_to_float(raw)
    if audio.ndim == 2:
        audio = np.mean(audio, axis=1)
    elif audio.ndim != 1:
        raise ValueError("WAV data must be mono or stereo/multichannel")
    if not np.all(np.isfinite(audio)):
        raise ValueError("WAV contains invalid samples")
    resampled = _resample(audio, int(source_rate), int(target_sample_rate))
    return np.clip(resampled, -1.0, 1.0), int(target_sample_rate)


def list_input_devices() -> list[dict[str, Any]]:
    """Return microphone-capable devices without exposing sounddevice objects."""

    sd = _require_sounddevice()
    try:
        devices = sd.query_devices()
    except Exception as error:
        raise RuntimeError(f"unable to enumerate audio devices: {error}") from error
    result: list[dict[str, Any]] = []
    for index, device in enumerate(devices):
        channels = int(device.get("max_input_channels", 0))
        if channels > 0:
            result.append(
                {
                    "index": index,
                    "name": str(device.get("name", f"Device {index}")),
                    "max_input_channels": channels,
                    "default_samplerate": float(device.get("default_samplerate", 0.0)),
                }
            )
    return result


def capture_microphone(
    duration: float,
    sample_rate: int,
    device: int | str | None = None,
    stop_event: threading.Event | None = None,
) -> np.ndarray:
    """Capture mono microphone audio with cooperative cancellation."""

    if duration <= 0 or sample_rate <= 0:
        raise ValueError("duration and sample_rate must be positive")
    sd = _require_sounddevice()
    total_samples = round(duration * sample_rate)
    block_size = min(1024, total_samples)
    collected: list[np.ndarray] = []
    captured = 0
    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device,
            blocksize=block_size,
        ) as stream:
            while captured < total_samples:
                if stop_event is not None and stop_event.is_set():
                    break
                frames = min(block_size, total_samples - captured)
                data, _overflowed = stream.read(frames)
                block = np.asarray(data[:, 0], dtype=np.float64)
                collected.append(block)
                captured += len(block)
    except Exception as error:
        raise RuntimeError(f"unable to record from microphone: {error}") from error
    if not collected:
        return np.zeros(0, dtype=np.float64)
    return np.concatenate(collected)[:total_samples]
