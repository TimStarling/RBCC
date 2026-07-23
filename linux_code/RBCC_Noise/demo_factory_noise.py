from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.io import wavfile


def generate_factory_noise(
    sample_rate: int = 16_000,
    duration_s: float = 5.0,
    seed: int = 42,
) -> np.ndarray:
    """Create repeatable synthetic factory noise for demonstrations."""

    if sample_rate <= 0 or duration_s <= 0:
        raise ValueError("sample_rate and duration_s must be positive")
    rng = np.random.default_rng(seed)
    sample_count = round(sample_rate * duration_s)
    time = np.arange(sample_count, dtype=np.float64) / sample_rate

    low_frequency_machinery = 0.24 * np.sin(2 * np.pi * 120.0 * time)
    motor_tone = 0.26 * np.sin(2 * np.pi * 980.0 * time)
    motor_harmonic = 0.13 * np.sin(2 * np.pi * 1960.0 * time)
    high_band_tool = 0.09 * np.sin(2 * np.pi * 3150.0 * time)

    white = rng.normal(0.0, 1.0, sample_count)
    # A lightweight low-pass recursion gives the broadband component a pink-like tilt.
    pinkish = np.empty_like(white)
    state = 0.0
    for index, value in enumerate(white):
        state = 0.985 * state + 0.15 * value
        pinkish[index] = state
    pinkish /= max(float(np.max(np.abs(pinkish))), 1e-12)
    broadband = 0.14 * pinkish

    transient = np.zeros(sample_count, dtype=np.float64)
    for center_s in (0.9, 2.6, 4.1):
        center = int(center_s * sample_rate)
        if center >= sample_count:
            continue
        length = min(int(0.018 * sample_rate), sample_count - center)
        envelope = np.exp(-np.linspace(0.0, 6.0, length))
        transient[center : center + length] += 0.65 * envelope * rng.choice((-1.0, 1.0), size=length)

    audio = (
        low_frequency_machinery
        + motor_tone
        + motor_harmonic
        + high_band_tool
        + broadband
        + transient
    )
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio = 0.82 * audio / peak
    return np.asarray(audio, dtype=np.float64)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成模拟厂房噪声 WAV 文件。")
    parser.add_argument("--output", type=Path, default=Path("demo_factory_noise.wav"))
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    audio = generate_factory_noise(args.sample_rate, args.duration, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.int16(np.round(np.clip(audio, -1.0, 1.0) * 32767.0))
    wavfile.write(args.output, args.sample_rate, pcm)
    print(f"已生成模拟厂房噪声：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
