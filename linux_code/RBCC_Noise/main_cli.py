from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from alarm_generator import generate_alarm, play_audio
from audio_input import capture_microphone, list_input_devices, load_wav
from config import AlarmConfig
from frequency_selector import select_warning_frequencies
from noise_analyzer import analyze_noise
from result_exporter import export_results


NOISE_TYPE_LABELS = {
    "low_level": "低电平输入",
    "transient": "瞬态冲击噪声",
    "tonal": "固定频率/带状噪声",
    "broadband_mixed": "宽频混合噪声",
    "steady_background": "稳态背景噪声",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="厂房噪声感知型自适应警告器：分析噪声并输出最佳警告频率。"
    )
    parser.add_argument("--source", choices=("microphone", "file"), default="microphone")
    parser.add_argument("--input", type=Path, help="WAV 文件路径（source=file 时必填）")
    parser.add_argument("--device", help="麦克风设备编号或名称")
    parser.add_argument("--duration", type=float, default=2.0, help="麦克风采集时长，单位秒")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--volume", type=float, default=0.35, help="警告音幅度，范围 0~1")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--no-play", action="store_true", help="不播放生成的警告音")
    parser.add_argument("--no-export", action="store_true", help="不导出 PNG/CSV/JSON/WAV")
    parser.add_argument("--list-devices", action="store_true", help="列出可用麦克风后退出")
    return parser


def _parse_device(value: str | None) -> int | str | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _print_devices() -> int:
    devices = list_input_devices()
    if not devices:
        print("没有检测到可用麦克风。")
        return 1
    for device in devices:
        print(
            f"[{device['index']}] {device['name']} | "
            f"输入通道: {device['max_input_channels']} | "
            f"默认采样率: {device['default_samplerate']:.0f} Hz"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_devices:
        try:
            return _print_devices()
        except RuntimeError as error:
            print(f"错误：{error}", file=sys.stderr)
            return 2

    try:
        config = AlarmConfig(
            sample_rate=args.sample_rate,
            analysis_duration=args.duration,
            alarm_volume=args.volume,
            output_root=args.output_dir,
        )
        config.validate()

        if args.source == "file":
            if args.input is None:
                parser.error("--source file 需要提供 --input WAV文件")
            audio, sample_rate = load_wav(args.input, config.sample_rate)
        else:
            print(f"正在采集麦克风声音，时长 {config.analysis_duration:.1f} 秒……")
            audio = capture_microphone(
                config.analysis_duration,
                config.sample_rate,
                device=_parse_device(args.device),
            )
            sample_rate = config.sample_rate
            if audio.size == 0:
                raise RuntimeError("没有采集到音频样本")

        started = time.perf_counter()
        analysis = analyze_noise(audio, sample_rate, config)
        selection = select_warning_frequencies(analysis, config)
        alarm_audio = generate_alarm(selection.frequencies_hz, config)
        processing_ms = (time.perf_counter() - started) * 1000.0

        print("\n=== 分析结果 ===")
        print(f"噪声类型：{NOISE_TYPE_LABELS.get(analysis.noise_type, analysis.noise_type)}")
        print(f"输入 RMS：{analysis.rms:.6f}")
        print(f"频谱平坦度：{analysis.spectral_flatness:.4f}")
        if analysis.dominant_peaks_hz:
            peaks = ", ".join(f"{value:.0f} Hz" for value in analysis.dominant_peaks_hz[:5])
            print(f"主要噪声峰值：{peaks}")
        else:
            print("主要噪声峰值：未检测到明显窄带峰值")
        print("最佳警告频率：")
        for index, choice in enumerate(selection.choices, start=1):
            print(
                f"  {index}. {choice.frequency_hz:.0f} Hz "
                f"(评分 {choice.score:.3f}, 局部噪声 {choice.local_noise_db:.1f} dB)"
            )
        print(f"算法处理耗时：{processing_ms:.2f} ms")
        if analysis.input_clipping:
            print("提醒：输入存在削波，建议降低麦克风增益。")

        if not args.no_export:
            exported = export_results(
                analysis,
                selection,
                alarm_audio,
                config,
                processing_ms=processing_ms,
                output_root=args.output_dir,
            )
            print(f"结果已保存：{exported.output_dir}")

        if not args.no_play:
            print("正在播放警告音……")
            play_audio(alarm_audio, config.sample_rate)
        return 0
    except SystemExit:
        raise
    except (ValueError, FileNotFoundError, RuntimeError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
