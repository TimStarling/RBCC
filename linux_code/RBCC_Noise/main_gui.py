from __future__ import annotations

import threading
import time
import tkinter as tk
from queue import Empty, Queue
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from alarm_generator import generate_alarm, play_audio
from audio_input import capture_microphone, list_input_devices, load_wav
from config import AlarmConfig
from frequency_selector import select_warning_frequencies
from models import NoiseAnalysis, SelectionResult
from noise_analyzer import analyze_noise
from result_exporter import export_results


NOISE_TYPE_LABELS = {
    "low_level": "低电平输入",
    "transient": "瞬态冲击噪声",
    "tonal": "固定频率/带状噪声",
    "broadband_mixed": "宽频混合噪声",
    "steady_background": "稳态背景噪声",
}


class AlarmApp:
    """Tkinter front end for microphone/WAV adaptive alarm analysis."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("厂房噪声感知型自适应警告器")
        self.root.geometry("1180x760")
        self.root.minsize(1000, 680)

        self.source_var = tk.StringVar(value="microphone")
        self.device_var = tk.StringVar()
        self.file_var = tk.StringVar()
        self.duration_var = tk.DoubleVar(value=2.0)
        self.volume_var = tk.DoubleVar(value=0.35)
        self.auto_play_var = tk.BooleanVar(value=True)
        self.auto_save_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="准备就绪")
        self.noise_type_var = tk.StringVar(value="—")
        self.peaks_var = tk.StringVar(value="—")
        self.timing_var = tk.StringVar(value="—")

        self.stop_event = threading.Event()
        self.event_queue: Queue[tuple[str, tuple[object, ...]]] = Queue()
        self.closing = False
        self.worker: threading.Thread | None = None
        self.device_map: dict[str, int] = {}
        self.latest_analysis: NoiseAnalysis | None = None
        self.latest_selection: SelectionResult | None = None
        self.latest_alarm: np.ndarray | None = None
        self.latest_config: AlarmConfig | None = None
        self.latest_processing_ms = 0.0

        self._build_ui()
        self._refresh_devices()
        self._update_source_controls()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._process_worker_events)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        controls = ttk.LabelFrame(outer, text="输入与控制", padding=10)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew")
        controls.columnconfigure(5, weight=1)

        ttk.Label(controls, text="输入来源：").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            controls,
            text="麦克风",
            value="microphone",
            variable=self.source_var,
            command=self._update_source_controls,
        ).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            controls,
            text="WAV 文件",
            value="file",
            variable=self.source_var,
            command=self._update_source_controls,
        ).grid(row=0, column=2, sticky="w")

        ttk.Label(controls, text="采集时长（秒）：").grid(row=0, column=3, padx=(16, 4))
        ttk.Spinbox(controls, from_=0.5, to=20.0, increment=0.5, textvariable=self.duration_var, width=8).grid(
            row=0, column=4
        )
        ttk.Label(controls, text="警告音量：").grid(row=0, column=5, padx=(16, 4), sticky="e")
        ttk.Scale(controls, from_=0.05, to=0.8, variable=self.volume_var, orient=tk.HORIZONTAL).grid(
            row=0, column=6, sticky="ew", padx=(0, 8)
        )

        ttk.Label(controls, text="麦克风：").grid(row=1, column=0, pady=(8, 0), sticky="w")
        self.device_combo = ttk.Combobox(controls, textvariable=self.device_var, state="readonly", width=42)
        self.device_combo.grid(row=1, column=1, columnspan=3, pady=(8, 0), sticky="ew")
        self.refresh_button = ttk.Button(controls, text="刷新设备", command=self._refresh_devices)
        self.refresh_button.grid(row=1, column=4, pady=(8, 0), padx=(6, 0))

        ttk.Label(controls, text="WAV 文件：").grid(row=2, column=0, pady=(8, 0), sticky="w")
        self.file_entry = ttk.Entry(controls, textvariable=self.file_var)
        self.file_entry.grid(row=2, column=1, columnspan=5, pady=(8, 0), sticky="ew")
        self.browse_button = ttk.Button(controls, text="选择文件", command=self._browse_file)
        self.browse_button.grid(row=2, column=6, pady=(8, 0), padx=(6, 0))

        options = ttk.Frame(controls)
        options.grid(row=3, column=0, columnspan=7, pady=(10, 0), sticky="ew")
        ttk.Checkbutton(options, text="分析后自动播放", variable=self.auto_play_var).pack(side=tk.LEFT)
        ttk.Checkbutton(options, text="分析后自动保存", variable=self.auto_save_var).pack(side=tk.LEFT, padx=(16, 0))
        self.start_button = ttk.Button(options, text="开始分析", command=self.start_analysis)
        self.start_button.pack(side=tk.LEFT, padx=(24, 6))
        self.stop_button = ttk.Button(options, text="停止", command=self.stop_analysis, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=6)
        self.play_button = ttk.Button(options, text="播放警告音", command=self.play_latest, state=tk.DISABLED)
        self.play_button.pack(side=tk.LEFT, padx=6)
        self.save_button = ttk.Button(options, text="保存结果", command=self.save_latest, state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=6)

        results = ttk.LabelFrame(outer, text="分析结果", padding=10)
        results.grid(row=1, column=0, sticky="nsew", pady=(12, 0), padx=(0, 10))
        results.columnconfigure(0, weight=1)
        results.rowconfigure(4, weight=1)

        ttk.Label(results, text="噪声类型", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(results, textvariable=self.noise_type_var, font=("TkDefaultFont", 13, "bold")).grid(
            row=1, column=0, sticky="w", pady=(2, 8)
        )
        ttk.Label(results, text="主要噪声峰值：").grid(row=2, column=0, sticky="w")
        ttk.Label(results, textvariable=self.peaks_var, wraplength=330).grid(row=3, column=0, sticky="w", pady=(2, 8))

        self.frequency_tree = ttk.Treeview(
            results,
            columns=("rank", "frequency", "score", "local_noise"),
            show="headings",
            height=8,
        )
        headings = {
            "rank": "序号",
            "frequency": "最佳频率",
            "score": "评分",
            "local_noise": "局部噪声",
        }
        widths = {"rank": 55, "frequency": 95, "score": 80, "local_noise": 105}
        for key in headings:
            self.frequency_tree.heading(key, text=headings[key])
            self.frequency_tree.column(key, width=widths[key], anchor=tk.CENTER)
        self.frequency_tree.grid(row=4, column=0, sticky="nsew")
        ttk.Label(results, text="处理耗时：").grid(row=5, column=0, sticky="w", pady=(10, 0))
        ttk.Label(results, textvariable=self.timing_var).grid(row=6, column=0, sticky="w")

        chart = ttk.LabelFrame(outer, text="实时频谱与最佳警告频率", padding=8)
        chart.grid(row=1, column=1, sticky="nsew", pady=(12, 0))
        chart.rowconfigure(0, weight=1)
        chart.columnconfigure(0, weight=1)
        self.figure = Figure(figsize=(7.3, 5.3), dpi=100)
        self.axis = self.figure.add_subplot(111)
        self.axis.set_xlabel("Frequency (Hz)")
        self.axis.set_ylabel("Mean power (dB)")
        self.axis.grid(True, alpha=0.25)
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        status = ttk.Label(outer, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w", padding=5)
        status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _refresh_devices(self) -> None:
        try:
            devices = list_input_devices()
            self.device_map = {
                f"[{device['index']}] {device['name']}": int(device["index"])
                for device in devices
            }
            names = list(self.device_map)
            self.device_combo["values"] = names
            if names:
                self.device_var.set(names[0])
                self.status_var.set(f"检测到 {len(names)} 个麦克风输入设备")
            else:
                self.device_var.set("")
                self.status_var.set("没有检测到麦克风，可使用 WAV 文件模式")
        except RuntimeError as error:
            self.device_map = {}
            self.device_combo["values"] = []
            self.device_var.set("")
            self.status_var.set(str(error))

    def _update_source_controls(self) -> None:
        microphone = self.source_var.get() == "microphone"
        self.device_combo.configure(state="readonly" if microphone else tk.DISABLED)
        self.refresh_button.configure(state=tk.NORMAL if microphone else tk.DISABLED)
        self.file_entry.configure(state=tk.DISABLED if microphone else tk.NORMAL)
        self.browse_button.configure(state=tk.DISABLED if microphone else tk.NORMAL)

    def _browse_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="选择厂房噪声 WAV 文件",
            filetypes=(("WAV audio", "*.wav"), ("All files", "*.*")),
        )
        if filename:
            self.file_var.set(filename)

    def _make_config(self) -> AlarmConfig:
        config = AlarmConfig(
            sample_rate=16000,
            analysis_duration=float(self.duration_var.get()),
            alarm_volume=float(self.volume_var.get()),
        )
        config.validate()
        return config

    def start_analysis(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        try:
            config = self._make_config()
            source = self.source_var.get()
            file_path = self.file_var.get().strip()
            device = self.device_map.get(self.device_var.get())
            auto_save = bool(self.auto_save_var.get())
            auto_play = bool(self.auto_play_var.get())
            previous = self.latest_selection.frequencies_hz if self.latest_selection else None
            if source == "file" and not file_path:
                raise ValueError("请选择 WAV 文件")
        except (ValueError, tk.TclError) as error:
            messagebox.showerror("参数错误", str(error))
            return

        self.stop_event.clear()
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.play_button.configure(state=tk.DISABLED)
        self.save_button.configure(state=tk.DISABLED)
        self.status_var.set("正在采集并分析噪声……")
        self.worker = threading.Thread(
            target=self._analysis_worker,
            args=(config, source, file_path, device, auto_save, auto_play, previous),
            daemon=True,
        )
        self.worker.start()

    def stop_analysis(self) -> None:
        self.stop_event.set()
        self.status_var.set("正在停止……")

    def _analysis_worker(
        self,
        config: AlarmConfig,
        source: str,
        file_path: str,
        device: int | None,
        auto_save: bool,
        auto_play: bool,
        previous: tuple[float, ...] | None,
    ) -> None:
        try:
            if source == "file":
                audio, sample_rate = load_wav(Path(file_path), config.sample_rate)
            else:
                audio = capture_microphone(
                    config.analysis_duration,
                    config.sample_rate,
                    device=device,
                    stop_event=self.stop_event,
                )
                sample_rate = config.sample_rate
            if self.stop_event.is_set():
                self.event_queue.put(("stopped", ()))
                return
            if audio.size == 0:
                raise RuntimeError("没有采集到音频样本")

            started = time.perf_counter()
            analysis = analyze_noise(audio, sample_rate, config)
            selection = select_warning_frequencies(analysis, config, previous)
            alarm = generate_alarm(selection.frequencies_hz, config)
            processing_ms = (time.perf_counter() - started) * 1000.0

            exported_dir: Path | None = None
            warnings: list[str] = []
            if auto_save:
                try:
                    exported = export_results(
                        analysis,
                        selection,
                        alarm,
                        config,
                        processing_ms=processing_ms,
                    )
                    exported_dir = exported.output_dir
                except Exception as error:
                    warnings.append(f"自动保存失败：{error}")
            if auto_play and not self.stop_event.is_set():
                try:
                    play_audio(alarm, config.sample_rate)
                except RuntimeError as error:
                    warnings.append(f"自动播放失败：{error}")

            self.event_queue.put(
                (
                    "success",
                    (
                        analysis,
                        selection,
                        alarm,
                        config,
                        processing_ms,
                        exported_dir,
                        tuple(warnings),
                    ),
                )
            )
        except Exception as error:
            self.event_queue.put(("error", (str(error),)))

    def _process_worker_events(self) -> None:
        if self.closing:
            return
        while True:
            try:
                event, payload = self.event_queue.get_nowait()
            except Empty:
                break
            if event == "success":
                self._finish_success(*payload)
            elif event == "stopped":
                self._finish_stopped()
            elif event == "error":
                self._finish_error(str(payload[0]))
            elif event == "play_error":
                messagebox.showerror("播放失败", str(payload[0]))
        self.root.after(100, self._process_worker_events)

    def _finish_success(
        self,
        analysis: NoiseAnalysis,
        selection: SelectionResult,
        alarm: np.ndarray,
        config: AlarmConfig,
        processing_ms: float,
        exported_dir: Path | None,
        warnings: tuple[str, ...],
    ) -> None:
        self.latest_analysis = analysis
        self.latest_selection = selection
        self.latest_alarm = alarm
        self.latest_config = config
        self.latest_processing_ms = processing_ms

        self.noise_type_var.set(NOISE_TYPE_LABELS.get(analysis.noise_type, analysis.noise_type))
        self.peaks_var.set(
            ", ".join(f"{value:.0f} Hz" for value in analysis.dominant_peaks_hz[:6])
            if analysis.dominant_peaks_hz
            else "未检测到明显窄带峰值"
        )
        self.timing_var.set(f"{processing_ms:.2f} ms")
        for item in self.frequency_tree.get_children():
            self.frequency_tree.delete(item)
        for index, choice in enumerate(selection.choices, start=1):
            self.frequency_tree.insert(
                "",
                tk.END,
                values=(
                    index,
                    f"{choice.frequency_hz:.0f} Hz",
                    f"{choice.score:.3f}",
                    f"{choice.local_noise_db:.1f} dB",
                ),
            )
        self._draw_spectrum(analysis, selection)
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.play_button.configure(state=tk.NORMAL)
        self.save_button.configure(state=tk.NORMAL)
        status = f"分析完成，结果已保存到 {exported_dir}" if exported_dir is not None else "分析完成"
        if warnings:
            status += "；" + "；".join(warnings)
        self.status_var.set(status)

    def _draw_spectrum(self, analysis: NoiseAnalysis, selection: SelectionResult) -> None:
        self.axis.clear()
        valid = analysis.frequencies_hz <= min(5000.0, analysis.sample_rate / 2.0)
        self.axis.plot(analysis.frequencies_hz[valid], analysis.mean_power_db[valid], linewidth=1.1)
        for choice in selection.choices:
            self.axis.axvline(choice.frequency_hz, linestyle="--", linewidth=1.0)
            self.axis.text(
                choice.frequency_hz,
                float(np.max(analysis.mean_power_db[valid])),
                f" {choice.frequency_hz:.0f}",
                rotation=90,
                va="top",
                fontsize=8,
            )
        self.axis.set_title(NOISE_TYPE_LABELS.get(analysis.noise_type, analysis.noise_type))
        self.axis.set_xlabel("Frequency (Hz)")
        self.axis.set_ylabel("Mean power (dB)")
        self.axis.grid(True, alpha=0.25)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _finish_stopped(self) -> None:
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("分析已停止")

    def _finish_error(self, message: str) -> None:
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("运行失败")
        messagebox.showerror("运行错误", message)

    def play_latest(self) -> None:
        if self.latest_alarm is None or self.latest_config is None:
            return
        threading.Thread(
            target=self._play_worker,
            args=(self.latest_alarm.copy(), self.latest_config.sample_rate),
            daemon=True,
        ).start()

    def _play_worker(self, audio: np.ndarray, sample_rate: int) -> None:
        try:
            play_audio(audio, sample_rate)
        except RuntimeError as error:
            self.event_queue.put(("play_error", (str(error),)))

    def save_latest(self) -> None:
        if not all((self.latest_analysis, self.latest_selection, self.latest_alarm is not None, self.latest_config)):
            return
        try:
            exported = export_results(
                self.latest_analysis,
                self.latest_selection,
                self.latest_alarm,
                self.latest_config,
                processing_ms=self.latest_processing_ms,
            )
            self.status_var.set(f"结果已保存到 {exported.output_dir}")
        except Exception as error:
            messagebox.showerror("保存失败", str(error))

    def _on_close(self) -> None:
        self.closing = True
        self.stop_event.set()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    AlarmApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
