#!/usr/bin/env python3
"""RBCC gantry-crane environment monitoring dashboard."""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from multiprocessing import shared_memory
from types import SimpleNamespace
from tkinter import ttk
from typing import Optional

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:
    raise SystemExit("缺少 pyserial，请执行：python3 -m pip install pyserial") from exc


APP_TITLE = "RBCC 龙门起重机环境监测平台"
SERIAL_BAUD = 115200
SERIAL_POLL_MS = 50
TCP_BIND_HOST = "0.0.0.0"
TCP_PORT = 8888
NOISE_PROJECT_DIR = "/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise"
NOISE_PYTHON = os.path.join(NOISE_PROJECT_DIR, ".venv", "bin", "python")
NOISE_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "noise_worker.py")
CAMERA_PROJECT_DIR = "/home/HwHiAiUser/Desktop/RBCC/RBCC_Camera"
CAMERA_PYTHON = "/usr/local/miniconda3/bin/python3.9"
CAMERA_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_worker.py")
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 360
CAMERA_FRAME_BYTES = CAMERA_WIDTH * CAMERA_HEIGHT * 3
CAMERA_CONTROL_FORMAT = "<QIIIfiii"
CAMERA_CONTROL_BYTES = struct.calcsize(CAMERA_CONTROL_FORMAT)
# This image is a proportionally fitted 1920×1080 rendering of the approved SVG.
# It fills the Orange Pi display without stretching Chinese text or the sandbox.
DASHBOARD_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor-dashboard-1920x1080.png")
# Installed alongside the interface in ~/.local/share/fonts.  This is used for
# every dynamic Chinese label drawn over the SVG background.
REFERENCE_FONT = "FZXiaoBiaoSong-B05S"
REFERENCE_LAYOUT_SCALE = 1.42
REFERENCE_LAYOUT_OFFSET_Y = -70
SERIAL_PATTERN = re.compile(
    r"tick=(?P<tick>\d+)\s+"
    r"mode=(?P<mode>\d+)\s+"
    r"light=(?P<light>\d+)%\s+raw=(?P<light_raw>\d+)\s+"
    r"temp=(?P<temp>[+-]?\d+(?:\.\d+)?)C\s+raw=(?P<temp_raw>\d+)"
    r"(?:\s+humidity=(?P<humidity>\d+)%)?"
    r"(?:\s*\(\s*(?P<x>-?\d+)\s*,\s*(?P<y>-?\d+)\s*\))?",
    re.IGNORECASE,
)

BEEP_MIN_HZ = 2000
BEEP_MAX_HZ = 5000
DANGER_LAMP_X_MIN = 6
DANGER_LAMP_X_MAX = 10
DANGER_FLASH_MS = 420


def encode_beep_command(frequency_hz: float) -> bytes:
    """Return the exact UTF-8 ``beep:XXXX`` serial command."""
    value = float(frequency_hz)
    if not math.isfinite(value):
        raise ValueError("beep frequency must be finite")

    frequency = int(round(value))
    if not BEEP_MIN_HZ <= frequency <= BEEP_MAX_HZ:
        raise ValueError("beep frequency must be within 2000-5000 Hz")

    payload = f"beep:{frequency:04d}".encode("utf-8")
    if len(payload) != 9:
        raise ValueError("beep command must contain exactly nine UTF-8 bytes")
    return payload


def write_beep_command(serial_port, frequency_hz: float) -> bytes:
    """Write one complete beep command and flush it to the serial device."""
    payload = encode_beep_command(frequency_hz)
    written = serial_port.write(payload)
    if written != len(payload):
        raise OSError(f"short serial write: {written}/{len(payload)} bytes")
    serial_port.flush()
    return payload

BG = "#061427"
PANEL = "#14263E"
HEADER = "#0B315F"
HEADER_ALT = "#104880"
BLUE = "#3385FF"
BLUE_2 = "#2A7DE1"
BLUE_SOFT = "#1E3553"
INK = "#F2F7FF"
MUTED = "#A9BCD4"
BORDER = "#315272"
GREEN = "#16D6B0"
AMBER = "#FFB547"
RED = "#FF5A5F"
CYAN = "#1AD4B3"


@dataclass(frozen=True)
class SensorFrame:
    tick: int
    mode: int
    light: int
    light_raw: int
    temperature: float
    temperature_raw: int
    humidity: Optional[int]
    x: Optional[int]
    y: Optional[int]


class _NoopMetric:
    """Keeps the serial pipeline active when the SVG dashboard is displayed."""

    def update_value(self, *_args) -> None:
        pass

    def set_stale(self) -> None:
        pass


class _NoopSandbox:
    def set_position(self, *_args) -> None:
        pass


class _NoopComponent:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def parse_sensor_line(line: str) -> Optional[SensorFrame]:
    match = SERIAL_PATTERN.search(line.strip())
    if not match:
        return None
    values = match.groupdict()
    humidity = values.get("humidity")
    x_value = values.get("x")
    y_value = values.get("y")
    return SensorFrame(
        tick=int(values["tick"]),
        mode=int(values["mode"]),
        light=int(values["light"]),
        light_raw=int(values["light_raw"]),
        temperature=float(values["temp"]),
        temperature_raw=int(values["temp_raw"]),
        humidity=int(humidity) if humidity is not None else None,
        x=int(x_value) if x_value is not None else None,
        y=int(y_value) if y_value is not None else None,
    )


def format_uptime(milliseconds: int) -> str:
    seconds = max(0, milliseconds // 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_local_position(x: int, y: int) -> bytes:
    """Encode an integer lamp coordinate for the STM32F4, without a newline."""
    return f"local:({int(x)},{int(y)})".encode("utf-8")


def physical_x_to_lamp_index(position_x_cm: float) -> int:
    """Map factory X=5..55 cm onto the 30 indexed lamps (0..29)."""
    scaled = (float(position_x_cm) - 5.0) / 50.0 * 29.0
    return int(max(0.0, min(29.0, scaled)))


def lamp_index_is_dangerous(lamp_x: Optional[int]) -> bool:
    """Return whether the live lamp X index is inside the danger zone."""
    return lamp_x is not None and DANGER_LAMP_X_MIN <= lamp_x <= DANGER_LAMP_X_MAX


class TcpSerialServer:
    """Single-cloud-client TCP listener with asynchronous byte forwarding."""

    def __init__(self, host: str = TCP_BIND_HOST, port: int = TCP_PORT):
        self.host = host
        self.port = port
        self.events = queue.Queue()
        self.outbound = queue.Queue(maxsize=256)
        self.latest_payload = b""
        self.latest_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.connected_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="rbcc-tcp-server", daemon=True)
        self.thread.start()

    def cache_latest(self, payload: bytes) -> None:
        """Remember the last complete sensor frame for newly connected clients."""
        if payload:
            with self.latest_lock:
                self.latest_payload = bytes(payload)

    def send(self, payload: bytes) -> None:
        if not payload or not self.connected_event.is_set():
            return
        try:
            self.outbound.put_nowait(bytes(payload))
        except queue.Full:
            self.events.put(("error", "TCP发送队列已满"))

    def stop(self) -> None:
        self.stop_event.set()
        self.connected_event.clear()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)

    def _run(self) -> None:
        listener = None
        client = None
        peer = None
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.host, self.port))
            listener.listen(5)
            listener.setblocking(False)
            self.events.put(("listening", self.port))

            while not self.stop_event.wait(0.03):
                try:
                    readable, _, _ = select.select([listener], [], [], 0)
                    if readable:
                        new_client, new_peer = listener.accept()
                        new_client.settimeout(0.25)
                        if client is not None:
                            try:
                                client.close()
                            except OSError:
                                pass
                        client, peer = new_client, new_peer
                        self.connected_event.set()
                        self.events.put(("connected", peer[0], peer[1]))
                        with self.latest_lock:
                            latest_payload = self.latest_payload
                        if latest_payload:
                            try:
                                client.sendall(latest_payload)
                            except OSError:
                                client.close()
                                client = None
                                self.connected_event.clear()
                except (OSError, ValueError):
                    if not self.stop_event.is_set():
                        raise

                if client is not None:
                    try:
                        readable, _, _ = select.select([client], [], [], 0)
                        if readable and client.recv(4096) == b"":
                            raise ConnectionError("peer closed")
                    except (OSError, ConnectionError, ValueError):
                        try:
                            client.close()
                        except OSError:
                            pass
                        client = None
                        self.connected_event.clear()
                        self.events.put(("disconnected", peer[0] if peer else ""))
                        peer = None

                while client is not None:
                    try:
                        payload = self.outbound.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        client.sendall(payload)
                    except OSError:
                        try:
                            client.close()
                        except OSError:
                            pass
                        client = None
                        self.connected_event.clear()
                        self.events.put(("disconnected", peer[0] if peer else ""))
                        peer = None
        except OSError as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.connected_event.clear()
            if client is not None:
                try:
                    client.close()
                except OSError:
                    pass
            if listener is not None:
                try:
                    listener.close()
                except OSError:
                    pass


class NoiseFrequencyMonitor:
    """Run the reference noise analyzer in its own virtual environment."""

    def __init__(self):
        self.events = queue.Queue()
        self.process: Optional[subprocess.Popen] = None
        self.reader: Optional[threading.Thread] = None
        self.stopping = False
        self.worker_log = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        if self.is_running():
            return
        self.stopping = False
        try:
            self.worker_log = open("/tmp/rbcc_noise_worker.log", "ab", buffering=0)
            self.process = subprocess.Popen(
                [NOISE_PYTHON, NOISE_WORKER],
                cwd=NOISE_PROJECT_DIR,
                stdout=subprocess.PIPE,
                stderr=self.worker_log,
                text=True,
                bufsize=1,
            )
        except (OSError, ValueError) as exc:
            self.events.put({"status": "worker_error", "message": str(exc)})
            self.process = None
            if self.worker_log:
                self.worker_log.close()
                self.worker_log = None
            return
        self.events.put({"status": "starting"})
        self.reader = threading.Thread(target=self._read_output, name="rbcc-noise-reader", daemon=True)
        self.reader.start()

    def _read_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            try:
                self.events.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        return_code = process.wait()
        if not self.stopping:
            self.events.put({"status": "worker_error", "message": f"噪声采集进程退出 ({return_code})"})

    def stop(self) -> None:
        self.stopping = True
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
        if process is not None and process.stdout is not None:
            process.stdout.close()
        if self.worker_log:
            self.worker_log.close()
            self.worker_log = None
        self.process = None


class RoundedPanel(tk.Canvas):
    def __init__(self, master: tk.Misc, *, background: str = PANEL, radius: int = 20, **kwargs):
        super().__init__(master, background=BG, highlightthickness=0, **kwargs)
        self.panel_background = background
        self.radius = radius
        self.body = tk.Frame(self, bg=background)
        self.window_id = self.create_window(0, 0, anchor="nw", window=self.body)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None) -> None:
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 2 or height <= 2:
            return
        self.delete("panel")
        r = min(self.radius, width // 2, height // 2)
        points = [
            r, 1, width - r, 1, width - 1, 1, width - 1, r,
            width - 1, height - r, width - 1, height - 1,
            width - r, height - 1, r, height - 1, 1, height - 1,
            1, height - r, 1, r, 1, 1,
        ]
        self.create_polygon(
            points,
            smooth=True,
            splinesteps=18,
            fill=self.panel_background,
            outline=BORDER,
            width=1,
            tags="panel",
        )
        self.tag_lower("panel")
        self.coords(self.window_id, 18, 16)
        self.itemconfigure(self.window_id, width=max(1, width - 36), height=max(1, height - 32))


class MetricCard(tk.Frame):
    def __init__(self, master: tk.Misc, icon: str, title: str, accent: str, unit: str,
                 detail_label: str = "ADC 原始值"):
        super().__init__(master, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, bd=0)
        self.accent = accent
        tk.Frame(self, bg=accent, width=4).place(relx=0, rely=0.08, relheight=0.84)
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill="x", padx=16, pady=(12, 3))
        tk.Label(top, text=icon, bg=PANEL, fg=INK, font=("DejaVu Sans", 18, "bold")).pack(side="left")
        tk.Label(top, text=title, bg=PANEL, fg=INK, font=("song ti", 15, "bold")).pack(side="left", padx=(8, 0))
        self.live_label = tk.Label(
            top, text="● 等待数据", bg=PANEL, fg=MUTED, font=("song ti", 10, "bold")
        )
        self.live_label.pack(side="right")

        value_row = tk.Frame(self, bg=PANEL)
        value_row.pack(fill="x", padx=16, pady=(3, 5))
        self.value_label = tk.Label(
            value_row, text="--", bg=PANEL, fg=accent, font=("DejaVu Sans", 31, "bold")
        )
        self.value_label.pack(side="left")
        tk.Label(
            value_row, text=unit, bg=PANEL, fg=MUTED, font=("song ti", 14, "bold")
        ).pack(side="left", padx=(6, 0), pady=(13, 0))

        self.bar = tk.Canvas(self, height=9, bg=PANEL, highlightthickness=0)
        self.bar.pack(fill="x", padx=16)
        self.bar.bind("<Configure>", lambda _event: self._draw_bar())
        self.level = 0.0

        footer = tk.Frame(self, bg=PANEL)
        footer.pack(fill="x", padx=16, pady=(7, 12))
        tk.Label(footer, text=detail_label, bg=PANEL, fg=MUTED,
                 font=("song ti", 10)).pack(side="left")
        self.raw_label = tk.Label(
            footer, text="--", bg="#0B1B2D", fg=INK, padx=10, pady=3, font=("DejaVu Sans Mono", 10, "bold")
        )
        self.raw_label.pack(side="right")

    def _draw_bar(self) -> None:
        width = max(1, self.bar.winfo_width())
        self.bar.delete("all")
        self.bar.create_rectangle(0, 1, width, 8, fill="#0B1B2D", outline="")
        self.bar.create_rectangle(0, 1, width * max(0.0, min(1.0, self.level)), 8, fill=self.accent, outline="")

    def update_value(self, value: str, raw, level: float) -> None:
        self.value_label.config(text=value)
        self.raw_label.config(text=str(raw))
        self.live_label.config(text="● 实时", fg=GREEN)
        self.level = level
        self._draw_bar()

    def set_stale(self) -> None:
        self.live_label.config(text="● 数据等待", fg=AMBER)


class SandboxView(tk.Canvas):
    def __init__(self, master: tk.Misc):
        super().__init__(master, bg=PANEL, highlightthickness=0)
        self.position_x = 15
        self.position_y = 15
        self.has_position = False
        self.bind("<Configure>", self._draw)

    def set_position(self, x: int, y: int) -> None:
        self.position_x = max(0, min(30, x))
        self.position_y = max(0, min(30, y))
        self.has_position = True
        self._draw()

    def _draw(self, _event=None) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 100 or height < 100:
            return
        title_y = 28
        self.create_text(26, title_y, anchor="w", text="☁  起重机位置沙盘", fill=INK,
                         font=("song ti", 18, "bold"))
        self.create_text(width - 26, title_y, anchor="e", text="坐标范围 0–30", fill=MUTED,
                         font=("song ti", 11))

        available_h = height - 92
        side = min(width - 74, available_h)
        x0 = (width - side) / 2
        y0 = 62 + (available_h - side) / 2
        x1, y1 = x0 + side, y0 + side

        self.create_rectangle(x0 + 10, y0 + 12, x1 + 10, y1 + 12, fill="#0B1B2D", outline="")
        self.create_rectangle(x0, y0, x1, y1, fill="#10243A", outline=BORDER, width=3)

        grid_color = "#294861"
        for index in range(1, 8):
            offset = side * index / 8
            self.create_line(x0 + offset, y0, x0 + offset, y1, fill=grid_color, dash=(4, 7))
            self.create_line(x0, y0 + offset, x1, y0 + offset, fill=grid_color, dash=(4, 7))

        rail = CYAN
        work_x0 = x0 + side * 0.13
        work_x1 = x1 - side * 0.13
        work_y0 = y0 + side * 0.08
        work_y1 = y1 - side * 0.08
        self.create_line(work_x0, work_y0, work_x0, work_y1, fill=rail, width=8)
        self.create_line(work_x1, work_y0, work_x1, work_y1, fill=rail, width=8)

        cx = work_x0 + (self.position_x / 30.0) * (work_x1 - work_x0)
        cy = work_y1 - (self.position_y / 30.0) * (work_y1 - work_y0)
        # Horizontal guide follows Y only; vertical guide follows X only.
        # Their crossing is always the live crane position.
        self.create_line(work_x0, cy, work_x1, cy, fill=BLUE, width=8)
        self.create_line(cx, work_y0, cx, work_y1, fill="#DCEBFF", width=2, dash=(5, 8))
        self.create_oval(cx - 24, cy - 24, cx + 24, cy + 24, fill="#3E2230", outline="")
        self.create_oval(cx - 11, cy - 11, cx + 11, cy + 11, fill=RED, outline="#FFB0B4", width=2)
        label_y = cy + 40 if cy < work_y1 - 55 else cy - 40
        position_text = f"({self.position_x}, {self.position_y})" if self.has_position else "(--, --)"
        self.create_text(cx, label_y, text=position_text, fill=RED,
                         font=("song ti", 9, "bold"))
        self.create_text(cx, y1 + 25, text="X 向右 · Y 向上 · 红点与龙门梁实时更新", fill=MUTED,
                         font=("song ti", 10))


class CameraMeasurementPanel(tk.Frame):
    """Compact processed-camera panel embedded in the monitoring dashboard."""

    def __init__(self, master: tk.Misc, position_callback=None):
        super().__init__(master, bg=BG)
        self.position_callback = position_callback
        self.last_position = None
        self.worker: Optional[subprocess.Popen] = None
        self.worker_log = None
        self.update_job = None
        self.running = False
        self.original_shm = None
        self.result_shm = None
        self.control_shm = None
        self.last_sequence = 0
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        toolbar.pack(fill="x", pady=(0, 6), ipady=5)
        tk.Label(toolbar, text="▣  白色物体识别结果", bg=PANEL, fg=INK,
                 font=("song ti", 13, "bold")).pack(side="left", padx=(12, 8))
        self.camera_button = tk.Button(
            toolbar, text="启动摄像头", command=self.toggle, cursor="hand2", relief="flat", bd=0,
            bg=BLUE_2, fg="white", activebackground=BLUE, activeforeground="white",
            padx=10, pady=5, font=("song ti", 9, "bold"),
        )
        self.camera_button.pack(side="right", padx=(6, 10))
        self.camera_status = tk.Label(
            toolbar, text="摄像头未启动", bg="#0B1B2D", fg=MUTED, padx=9, pady=5,
            font=("song ti", 9, "bold"),
        )
        self.camera_status.pack(side="right")

        panel = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        panel.pack(fill="both", expand=True)
        tk.Label(panel, text="实时监控画面", bg=PANEL, fg=INK,
                 font=("song ti", 12, "bold")).pack(anchor="w", padx=10, pady=(7, 4))
        self.result_label = tk.Label(
            panel, text="等待摄像头画面", bg="#0D1726", fg="#93A8C5",
            font=("song ti", 11), compound="center",
        )
        self.result_label.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def toggle(self) -> None:
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.running:
            return
        self.camera_status.config(text="正在打开摄像头…", fg=AMBER)
        self.update_idletasks()
        try:
            self.original_shm = shared_memory.SharedMemory(create=True, size=CAMERA_FRAME_BYTES * 2)
            self.result_shm = shared_memory.SharedMemory(create=True, size=CAMERA_FRAME_BYTES * 2)
            self.control_shm = shared_memory.SharedMemory(create=True, size=CAMERA_CONTROL_BYTES)
            self.control_shm.buf[:CAMERA_CONTROL_BYTES] = bytes(CAMERA_CONTROL_BYTES)
            self.worker_log = open("/tmp/rbcc_camera_worker.log", "ab", buffering=0)
            self.worker = subprocess.Popen(
                [
                    CAMERA_PYTHON, CAMERA_WORKER,
                    "--width", str(CAMERA_WIDTH), "--height", str(CAMERA_HEIGHT),
                    "--original-shm", self.original_shm.name,
                    "--result-shm", self.result_shm.name,
                    "--control-shm", self.control_shm.name,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=self.worker_log,
                close_fds=True,
            )
        except Exception as exc:
            self._release_camera()
            self.camera_status.config(text="摄像头启动失败", fg=RED)
            self.result_label.config(text=f"无法打开摄像头\n{exc}", image="")
            return

        self.running = True
        self.last_sequence = 0
        self.camera_button.config(text="停止摄像头", bg="#EAF2FF", fg=BLUE)
        self.camera_status.config(text="摄像头正在预热", fg=AMBER)
        self._update_frames()

    def stop(self) -> None:
        if self.update_job is not None:
            try:
                self.after_cancel(self.update_job)
            except tk.TclError:
                pass
            self.update_job = None
        self.running = False
        self._release_camera()
        self.camera_button.config(text="启动摄像头", bg=BLUE_2, fg="white")
        self.camera_status.config(text="摄像头已释放", fg=MUTED)
        self.result_label.config(image="", text="等待摄像头画面")
        self.result_label.image = None

    def _release_camera(self) -> None:
        if self.worker is not None:
            if self.worker.poll() is None:
                self.worker.terminate()
                try:
                    self.worker.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.worker.kill()
                    self.worker.wait(timeout=1)
            self.worker = None
        if self.worker_log is not None:
            self.worker_log.close()
            self.worker_log = None
        for attribute in ("original_shm", "result_shm", "control_shm"):
            block = getattr(self, attribute)
            if block is not None:
                block.close()
                try:
                    block.unlink()
                except FileNotFoundError:
                    pass
                setattr(self, attribute, None)

    @staticmethod
    def _load_photo(rgb: bytes, width: int, height: int):
        ppm = f"P6\n{width} {height}\n255\n".encode("ascii") + rgb
        return tk.PhotoImage(data=ppm, format="PPM")

    def _update_frames(self) -> None:
        self.update_job = None
        if (not self.running or self.worker is None or self.result_shm is None
                or self.control_shm is None):
            return
        try:
            sequence, width, height, frame_bytes, fps, position_valid, position_x, position_y = struct.unpack_from(
                CAMERA_CONTROL_FORMAT, self.control_shm.buf, 0
            )
            if sequence > self.last_sequence and frame_bytes == CAMERA_FRAME_BYTES:
                slot = sequence & 1
                offset = slot * frame_bytes
                result_rgb = bytes(self.result_shm.buf[offset:offset + frame_bytes])
                current_sequence = struct.unpack_from("<Q", self.control_shm.buf, 0)[0]
                if current_sequence != sequence:
                    self.update_job = self.after(15, self._update_frames)
                    return
                result_photo = self._load_photo(result_rgb, width, height)
                self.result_label.config(image=result_photo, text="")
                self.result_label.image = result_photo
                self.last_sequence = sequence
                self.camera_status.config(text=f"运行中 · {fps:.1f} FPS", fg=GREEN)
                if position_valid:
                    current_position = (position_x, position_y)
                    if current_position != self.last_position:
                        self.last_position = current_position
                    if self.position_callback is not None:
                        self.position_callback(position_x, position_y)
                elif self.last_position is not None:
                    self.last_position = None
                    if self.position_callback is not None:
                        self.position_callback(None, None)
        except Exception as exc:
            self.camera_status.config(text=f"处理异常: {exc}", fg=RED)
        if self.worker.poll() is not None:
            self.camera_status.config(text="摄像头进程已退出", fg=RED)
        else:
            self.update_job = self.after(30, self._update_frames)


class Dashboard(tk.Tk):
    def __init__(self, demo: bool = False):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=BG)
        self.minsize(1280, 760)
        try:
            self.attributes("-zoomed", True)
        except tk.TclError:
            self.geometry("1600x900")
        self.demo = demo
        self.serial_port: Optional[serial.Serial] = None
        self.serial_buffer = ""
        self.last_frame_at = 0.0
        self.packet_count = 0
        self.first_packet_at = 0.0
        self.camera_position: Optional[tuple[int, int]] = None
        self.last_sent_lamp_position: Optional[tuple[int, int]] = None
        self.pending_lamp_position: Optional[tuple[int, int]] = None
        self.pending_lamp_frames = 0
        self.danger_warning_active = False
        self.danger_flash_on = False
        self.danger_flash_job: Optional[str] = None
        self.current_port = ""
        # The monitor is a fixed 1920×1080 Orange Pi panel.  Fullscreen keeps
        # the dashboard's bottom component from being cut by the desktop bar.
        self.fullscreen = True
        self.attributes("-fullscreen", True)
        self.tcp_server = TcpSerialServer()
        self.noise_monitor = NoiseFrequencyMonitor()

        self.protocol("WM_DELETE_WINDOW", self.close)
        signal.signal(signal.SIGTERM, lambda *_args: self.after_idle(self.close))
        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", self.leave_fullscreen)

        self._build_styles()
        # The reference dashboard is the approved visual design.  Its values
        # are painted by Canvas from real serial frames; it is not a mock page.
        self._build_svg_dashboard()
        self.tcp_server.start()
        self.refresh_ports()
        self.after(150, self.poll_serial)
        self.after(100, self.poll_tcp_events)
        self.after(450, self.noise_monitor.start)
        self.after(200, self.poll_noise_events)
        self.after(4000, self.maintain_noise_monitor)
        self.after(500, self.refresh_clock)
        self.after(850, self.auto_connect)
        self.after(2000, self.maintain_serial_connection)
        if demo:
            self.after(350, lambda: self.handle_line(
                "tick=256002 mode=1 light=93% raw=308 temp=+41.41C raw=994 humidity=50% (125,125)"
            ))

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Port.TCombobox", padding=8, font=("song ti", 11),
                        fieldbackground=PANEL, background=PANEL, foreground=INK)

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=HEADER, height=106)
        header.pack(fill="x", padx=20, pady=(18, 10))
        header.pack_propagate(False)
        title_box = tk.Frame(header, bg=HEADER)
        title_box.pack(side="left", fill="y", padx=28, pady=13)
        tk.Label(title_box, text="龙门起重机环境监测平台", bg=HEADER, fg="white",
                 font=("song ti", 25, "bold")).pack(anchor="w")
        tk.Label(title_box, text="RBCC  环境传感 · 位置沙盘 · 视觉识别实时监控", bg=HEADER, fg="#BBD8FF",
                 font=("song ti", 11, "bold")).pack(anchor="w", pady=(3, 0))
        header_right = tk.Frame(header, bg=HEADER)
        header_right.pack(side="right", fill="y", padx=26, pady=12)
        self.clock_label = tk.Label(header_right, text="", bg=HEADER_ALT, fg="white", padx=18, pady=7,
                                    font=("DejaVu Sans", 12, "bold"))
        self.clock_label.pack(anchor="e")
        self.header_status = tk.Label(header_right, text="● 串口未连接", bg=HEADER, fg="#DCEBFF",
                                      font=("song ti", 11, "bold"))
        self.header_status.pack(anchor="e", pady=(10, 0))

        toolbar = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        toolbar.pack(fill="x", padx=20, pady=(0, 10), ipady=8)
        tk.Label(toolbar, text="⌁  串口检测", bg=PANEL, fg=INK,
                 font=("song ti", 15, "bold")).pack(side="left", padx=(18, 12))
        self.port_combo = ttk.Combobox(toolbar, state="readonly", style="Port.TCombobox", width=38)
        self.port_combo.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.refresh_button = self._button(toolbar, "↻ 刷新端口", self.refresh_ports, secondary=True)
        self.refresh_button.pack(side="left", padx=5)
        self.connect_button = self._button(toolbar, "连接串口", self.toggle_serial)
        self.connect_button.pack(side="left", padx=5)
        self.port_status = tk.Label(toolbar, text="等待连接", bg="#0B1B2D", fg=MUTED, padx=14, pady=7,
                                    font=("song ti", 10, "bold"))
        self.port_status.pack(side="left", padx=(10, 18))

        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        content.grid_columnconfigure(0, weight=26, uniform="columns")
        content.grid_columnconfigure(1, weight=40, uniform="columns")
        content.grid_columnconfigure(2, weight=38, uniform="columns")
        content.grid_rowconfigure(0, weight=1)

        left = tk.Frame(content, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        for row in range(4):
            left.grid_rowconfigure(row, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.light_card = MetricCard(left, "☀", "环境光照", BLUE_2, "%")
        self.light_card.grid(row=0, column=0, sticky="nsew", pady=(0, 4))
        self.temp_card = MetricCard(left, "◉", "环境温度", RED, "°C")
        self.temp_card.grid(row=1, column=0, sticky="nsew", pady=4)
        self.humidity_card = MetricCard(left, "☁", "环境湿度", CYAN, "%", "测量类型")
        self.humidity_card.grid(row=2, column=0, sticky="nsew", pady=4)

        system = tk.Frame(left, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        system.grid(row=3, column=0, sticky="nsew", pady=(4, 0))
        system_header = tk.Frame(system, bg=PANEL)
        system_header.pack(fill="x", padx=14, pady=(9, 5))
        tk.Label(system_header, text="⚙  系统状态", bg=PANEL, fg=INK,
                 font=("song ti", 14, "bold")).pack(side="left")
        self.cloud_value = tk.Label(system_header, text=f"● 云端等待 TCP {TCP_PORT}",
                                    bg=PANEL, fg=AMBER,
                                    font=("song ti", 9, "bold"))
        self.cloud_value.pack(side="right")
        grid = tk.Frame(system, bg=PANEL)
        grid.pack(fill="both", expand=True, padx=10, pady=(0, 9))
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1)
        self.mode_value = self._status_tile(grid, "运行模式", 0, 0, BLUE)
        self.tick_value = self._status_tile(grid, "设备运行时间", 0, 1, GREEN)
        self.uptime_value = self._status_tile(grid, "运行时长", 1, 0, AMBER)
        self.rate_value = self._status_tile(grid, "接收频率", 1, 1, RED)

        center = RoundedPanel(content)
        center.grid(row=0, column=1, sticky="nsew", padx=4)
        self.sandbox = SandboxView(center.body)
        self.sandbox.pack(fill="both", expand=True)

        right = tk.Frame(content, bg=BG)
        right.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(2, weight=3)

        latest = tk.Frame(right, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        latest.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tk.Label(latest, text="▣  最新数据", bg=PANEL, fg=INK,
                 font=("song ti", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        self.latest_line = tk.Label(latest, text="等待串口数据…", bg="#0B1B2D", fg="#BBD8FF",
                                    justify="left", anchor="nw", wraplength=600, padx=12, pady=9,
                                    font=("DejaVu Sans Mono", 9))
        self.latest_line.pack(fill="x", padx=10, pady=(0, 9))

        noise_panel = tk.Frame(right, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        noise_panel.grid(row=1, column=0, sticky="new", pady=(0, 6))
        noise_header = tk.Frame(noise_panel, bg=PANEL)
        noise_header.pack(fill="x", padx=12, pady=(7, 4))
        tk.Label(noise_header, text="⌁  现场噪声分析", bg=PANEL, fg=INK,
                 font=("song ti", 13, "bold")).pack(side="left")
        self.noise_status = tk.Label(noise_header, text="准备自动采集", bg=PANEL, fg=AMBER,
                                     font=("song ti", 9, "bold"))
        self.noise_status.pack(side="right")
        noise_values = tk.Frame(noise_panel, bg=PANEL)
        noise_values.pack(fill="x", padx=9, pady=(0, 9))
        noise_values.grid_columnconfigure(0, weight=1, uniform="noise")
        noise_values.grid_columnconfigure(1, weight=1, uniform="noise")
        max_tile = tk.Frame(noise_values, bg=BLUE_SOFT, highlightbackground=BORDER, highlightthickness=1)
        max_tile.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        tk.Label(max_tile, text="现场最大噪声频率", bg=BLUE_SOFT, fg=MUTED,
                 font=("song ti", 9)).pack(anchor="w", padx=10, pady=(7, 1))
        self.max_noise_frequency = tk.Label(max_tile, text="-- Hz", bg=BLUE_SOFT, fg=INK,
                                            font=("DejaVu Sans", 17, "bold"))
        self.max_noise_frequency.pack(anchor="w", padx=10, pady=(0, 7))
        alarm_tile = tk.Frame(noise_values, bg=BLUE_SOFT, highlightbackground=BORDER, highlightthickness=1)
        alarm_tile.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        tk.Label(alarm_tile, text="警告蜂鸣器最佳频率", bg=BLUE_SOFT, fg=MUTED,
                 font=("song ti", 9)).pack(anchor="w", padx=10, pady=(7, 1))
        self.best_alarm_frequency = tk.Label(alarm_tile, text="-- Hz", bg=BLUE_SOFT, fg=BLUE,
                                             font=("DejaVu Sans", 17, "bold"))
        self.best_alarm_frequency.pack(anchor="w", padx=10, pady=(0, 7))

        self.camera_panel = CameraMeasurementPanel(right)
        self.camera_panel.grid(row=2, column=0, sticky="nsew")

        footer = tk.Frame(self, bg=INK, height=36)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self.footer_status = tk.Label(footer, text="系统就绪", bg=INK, fg="#D8E5F7",
                                      font=("song ti", 10))
        self.footer_status.pack(side="left", padx=20)
        tk.Label(footer, text="F11 全屏 · Esc 退出全屏", bg=INK, fg="#8297B4",
                 font=("song ti", 9)).pack(side="right", padx=20)

        self.after(300, self.camera_panel.start)

    def _build_svg_dashboard(self) -> None:
        self.configure(bg="#061427")
        self.dashboard_image = tk.PhotoImage(file=DASHBOARD_IMAGE)
        # Keep icons/components proportionate and move the original composition
        # up, leaving a clear strip beneath the sandbox for latest data.
        self.reference_scale_x = REFERENCE_LAYOUT_SCALE
        self.reference_scale_y = REFERENCE_LAYOUT_SCALE
        self.reference_offset_x = (self.dashboard_image.width() - 1194 * REFERENCE_LAYOUT_SCALE) / 2.0
        self.reference_offset_y = REFERENCE_LAYOUT_OFFSET_Y
        self.reference_canvas = tk.Canvas(
            self, width=self.dashboard_image.width(), height=self.dashboard_image.height(),
            bg="#061427", highlightthickness=0, bd=0,
        )
        self.reference_canvas.place(relx=0.5, rely=0.5, anchor="center")
        self.reference_canvas.create_image(0, 0, image=self.dashboard_image, anchor="nw")
        self.reference_items: dict[str, int] = {}
        self.reference_frame: Optional[SensorFrame] = None
        self._reference_draw(None)

        # Place real controls over their SVG counterparts.  The design remains
        # unchanged, but refresh/connect/port selection work after boot.
        header_scale = REFERENCE_LAYOUT_SCALE
        header_x = self.reference_offset_x
        toolbar_y = round(89 * header_scale)
        self.port_combo = ttk.Combobox(
            self, state="readonly", style="Port.TCombobox",
            font=(REFERENCE_FONT, 13),
        )
        self.port_combo.place(
            x=round(header_x + 145 * header_scale), y=toolbar_y + 4,
            width=round(640 * header_scale), height=round(32 * header_scale),
        )
        self.refresh_button = tk.Button(
            self, text="刷新端口", command=self.refresh_ports, cursor="hand2", relief="flat", bd=0,
            bg="#1C263B", fg="white", activebackground="#30455F", activeforeground="white",
            font=(REFERENCE_FONT, 12, "bold"),
        )
        self.refresh_button.place(
            x=round(header_x + 828 * header_scale), y=toolbar_y,
            width=round(86 * header_scale), height=round(40 * header_scale),
        )
        self.connect_button = tk.Button(
            self, text="连接串口", command=self.toggle_serial, cursor="hand2", relief="flat", bd=0,
            bg="#EAF2FF", fg=BLUE, activebackground="#D9E9FF", activeforeground=BLUE,
            font=(REFERENCE_FONT, 12, "bold"),
        )
        self.connect_button.place(
            x=round(header_x + 925 * header_scale), y=toolbar_y,
            width=round(87 * header_scale), height=round(40 * header_scale),
        )
        self.port_status = tk.Label(self)
        self.header_status = tk.Label(self)
        self.footer_status = tk.Label(self)
        self.cloud_value = tk.Label(self)
        self.clock_label = tk.Label(self)
        self.latest_line = tk.Label(self)
        self.mode_value = tk.Label(self)
        self.tick_value = tk.Label(self)
        self.uptime_value = tk.Label(self)
        self.rate_value = tk.Label(self)
        self.max_noise_frequency = tk.Label(self)
        self.best_alarm_frequency = tk.Label(self)
        self.noise_status = tk.Label(self)
        self.light_card = _NoopMetric()
        self.temp_card = _NoopMetric()
        self.humidity_card = _NoopMetric()
        self.sandbox = _NoopSandbox()
        camera_x, camera_y = self._reference_point(828, 480)
        self.camera_panel = CameraMeasurementPanel(self, self.apply_camera_position)
        self.camera_panel.place(
            x=camera_x, y=camera_y,
            width=round(332 * REFERENCE_LAYOUT_SCALE),
            height=round(235 * REFERENCE_LAYOUT_SCALE),
        )
        self.after(500, self.camera_panel.start)

        # A real, clickable back control.  It returns to the Orange Pi desktop
        # without stopping the serial, TCP or camera workers.
        self.back_button = tk.Button(
            self, text="←", command=self.go_back, cursor="hand2",
            relief="flat", bd=0, bg="#1C263B", fg="#FFFFFF",
            activebackground="#30455F", activeforeground="#FFFFFF",
            font=("DejaVu Sans", 20, "bold"),
            highlightbackground="#6B89A8", highlightthickness=1,
        )
        self.back_button.place(relx=0.985, rely=0.975, anchor="se", width=58, height=44)

        # Floating warning banner. It stays above every dashboard component and
        # is shown only while the camera-derived lamp X index is within 6..10.
        self.danger_banner_shadow = tk.Frame(self, bg="#450006", bd=0)
        self.danger_banner = tk.Label(
            self, text="⚠  有人进入危险区  ⚠",
            bg="#FF2028", fg="#FFFFFF", relief="flat", bd=0,
            font=(REFERENCE_FONT, 30, "bold"), padx=28, pady=12,
        )

    def _reference_point(self, x: float, y: float) -> tuple[int, int]:
        return (
            round(self.reference_offset_x + x * self.reference_scale_x),
            round(self.reference_offset_y + y * self.reference_scale_y),
        )

    def apply_camera_position(self, x: Optional[int], y: Optional[int]) -> None:
        """Drive the sandbox from the live object detected in the camera view."""
        if x is None or y is None:
            new_position = None
        else:
            new_position = (max(0, min(60, x)), max(0, min(30, y)))
        changed = new_position != self.camera_position
        self.camera_position = new_position
        lamp_x = physical_x_to_lamp_index(new_position[0]) if new_position is not None else None
        self.set_danger_warning(lamp_index_is_dangerous(lamp_x))
        if new_position is not None:
            self.send_camera_position()
        if not changed:
            return
        if hasattr(self, "reference_canvas"):
            self._reference_draw(self.reference_frame)

    def set_danger_warning(self, active: bool) -> None:
        """Show or hide the floating, flashing danger-zone banner."""
        active = bool(active)
        if active == self.danger_warning_active:
            if active:
                self.danger_banner_shadow.lift()
                self.danger_banner.lift()
            return

        self.danger_warning_active = active
        if active:
            self.danger_flash_on = False
            self.danger_banner_shadow.place(
                relx=0.5, rely=0.505, anchor="center", relwidth=0.58, height=100,
            )
            self.danger_banner.place(
                relx=0.5, rely=0.495, anchor="center", relwidth=0.58, height=100,
            )
            self._flash_danger_warning()
        else:
            if self.danger_flash_job is not None:
                self.after_cancel(self.danger_flash_job)
                self.danger_flash_job = None
            self.danger_banner.place_forget()
            self.danger_banner_shadow.place_forget()

    def _flash_danger_warning(self) -> None:
        """Pulse the banner colours until the lamp leaves the danger zone."""
        if not self.danger_warning_active:
            self.danger_flash_job = None
            return
        self.danger_flash_on = not self.danger_flash_on
        if self.danger_flash_on:
            self.danger_banner.config(bg="#FF1F28", fg="#FFFFFF")
        else:
            self.danger_banner.config(bg="#B90012", fg="#FFE45C")
        self.danger_banner_shadow.lift()
        self.danger_banner.lift()
        self.danger_flash_job = self.after(DANGER_FLASH_MS, self._flash_danger_warning)

    def send_camera_position(self, force: bool = False) -> None:
        """Send the changed lamp coordinate over the already-open STM32 UART."""
        if self.camera_position is None or self.serial_port is None:
            return
        # The STM32 consumes lamp coordinates, not the 60 x 30 cm camera
        # coordinate.  There is currently one longitudinal lamp axis, so Y is
        # intentionally fixed at zero as required by its parser.
        lamp_position = (physical_x_to_lamp_index(self.camera_position[0]), 0)
        if not force:
            if lamp_position == self.last_sent_lamp_position:
                self.pending_lamp_position = None
                self.pending_lamp_frames = 0
                return
            if lamp_position == self.pending_lamp_position:
                self.pending_lamp_frames += 1
            else:
                self.pending_lamp_position = lamp_position
                self.pending_lamp_frames = 1
            # Suppress one-pixel oscillation at a lamp boundary while keeping
            # actual crane motion responsive (four frames is roughly 0.2 s).
            if self.pending_lamp_frames < 4:
                return
        try:
            payload = format_local_position(*lamp_position)
            self.serial_port.write(payload)
            self.serial_port.flush()
            self.last_sent_lamp_position = lamp_position
            self.pending_lamp_position = None
            self.pending_lamp_frames = 0
            print(f"SERIAL_TX {payload.decode('utf-8')}", flush=True)
        except (OSError, serial.SerialException, serial.SerialTimeoutException) as exc:
            self.footer_status.config(text=f"视觉坐标发送失败: {exc}")
            self.disconnect_serial("坐标发送异常")

    def _reference_box(self, x0: int, y0: int, x1: int, y1: int, fill: str) -> None:
        """Mask sample values in the approved background before drawing live values."""
        left, top = self._reference_point(x0, y0)
        right, bottom = self._reference_point(x1, y1)
        self.reference_canvas.create_rectangle(left, top, right, bottom, fill=fill, outline="", tags=("live-mask",))

    def _reference_line(self, x0: float, y0: float, x1: float, y1: float,
                        fill: str, width: float, dash=None) -> None:
        start = self._reference_point(x0, y0)
        end = self._reference_point(x1, y1)
        scaled_dash = tuple(round(value * self.reference_scale_y) for value in dash) if dash else None
        self.reference_canvas.create_line(
            *start, *end, fill=fill, width=max(1, round(width * self.reference_scale_y)),
            dash=scaled_dash, tags=("live-mask",),
        )

    def _reference_oval(self, x0: float, y0: float, x1: float, y1: float, fill: str) -> None:
        left, top = self._reference_point(x0, y0)
        right, bottom = self._reference_point(x1, y1)
        self.reference_canvas.create_oval(left, top, right, bottom, fill=fill, outline="", tags=("live-mask",))

    def _reference_text(self, key: str, x: int, y: int, text: str, fill: str,
                        size: int = 15, anchor: str = "w", font: str = REFERENCE_FONT) -> None:
        x, y = self._reference_point(x, y)
        size = max(9, round(size * self.reference_scale_y))
        item = self.reference_items.get(key)
        if item is None:
            self.reference_items[key] = self.reference_canvas.create_text(
                x, y, text=text, fill=fill, anchor=anchor, font=(font, size, "bold"),
                tags=("live-text",),
            )
        else:
            self.reference_canvas.coords(item, x, y)
            self.reference_canvas.itemconfigure(item, text=text, fill=fill, font=(font, size, "bold"), anchor=anchor)

    def _reference_draw(self, frame: Optional[SensorFrame]) -> None:
        """Draw dynamic values on the approved dashboard artwork.

        The image contributes only the background, labels and component chrome.
        Every sensor value, the latest line, status values and sandbox geometry
        below are supplied from the current frame (or '--' when none exists).
        """
        canvas = self.reference_canvas
        canvas.delete("live-mask")
        # Environmental values: cover the reference sample values and render live values.
        metric_rows = (("light", 250, "#2584FF", "%", "light_raw"),
                       ("temp", 450, "#FF4248", "°C", "temp_raw"),
                       ("humidity", 648, "#1AD4B3", "%", None))
        for name, y, color, unit, raw_name in metric_rows:
            self._reference_box(72, y, 214, y + 38, "#2A3A52")
            self._reference_box(258, y + 52, 330, y + 77, "#2A3A52")
            value = "--"
            raw = "--"
            level = 0
            if frame:
                if name == "light":
                    value, raw, level = str(frame.light), str(frame.light_raw), frame.light
                elif name == "temp":
                    value, raw, level = f"{frame.temperature:+.2f}", str(frame.temperature_raw), max(0, min(100, int(frame.temperature * 2)))
                else:
                    value, raw, level = str(frame.humidity), "RH", frame.humidity
            self._reference_text(f"{name}-value", 78, y + 18, f"{value}{unit if value != '--' else ''}", color, 24)
            self._reference_text(f"{name}-raw", 305, y + 64, raw, color if name != "humidity" else "#FFFFFF", 12, "e")
            # Replace the sample progress bar with a value-dependent bar.
            self._reference_box(77, y + 39, 329, y + 44, "#E7EEF7")
            self._reference_box(77, y + 39, 77 + int(252 * max(0, min(100, level)) / 100), y + 44, "#2C86FF")

        # System state and latest data.
        for box in ((872, 280, 973, 326), (1010, 280, 1112, 326), (872, 384, 973, 430), (1010, 384, 1128, 430)):
            self._reference_box(*box, "#2B3B53")
        mode = str(frame.mode) if frame else "--"
        elapsed = f"{frame.tick // 1000}秒" if frame else "--"
        duration = format_uptime(frame.tick) if frame else "--"
        rate = "-- Hz"
        if frame and self.last_frame_at and self.first_packet_at:
            rate = self.rate_value.cget("text") if hasattr(self.rate_value, "cget") else "-- Hz"
        self._reference_text("mode", 877, 294, mode, "#2C86FF", 19)
        self._reference_text("tick", 1016, 294, elapsed, "#1AD4B3", 18)
        self._reference_text("duration", 877, 397, duration, "#FFB51B", 17)
        self._reference_text("rate", 1018, 397, rate, "#FF4248", 13)
        # Latest data moves from the right column to its own compact strip
        # below the sandbox.  The right column is reserved for live video.
        latest = "等待串口数据…" if not frame else (
            f"tick={frame.tick} mode={frame.mode} light={frame.light}%\n"
            f"raw={frame.light_raw} temp={frame.temperature:+.2f}C raw={frame.temperature_raw}\n"
            f"humidity={frame.humidity}% ({frame.x},{frame.y})"
        )
        self._reference_text("latest", 430, 725, latest, "#FFFFFF", 9)

        # Camera-aligned 60 x 30 cm sandbox.  X runs left-to-right and Y runs
        # bottom-to-top, matching the rectified camera view.  Each physical LED
        # strip is 50 cm long with a 5 cm margin at both factory ends; its 30
        # indexed beads therefore occupy X=5..55 cm.
        factory_left, factory_right = 470, 742
        factory_top, factory_bottom = 350, 486
        factory_width = factory_right - factory_left
        factory_height = factory_bottom - factory_top
        strip_left = factory_left + 5.0 / 60.0 * factory_width
        strip_right = factory_left + 55.0 / 60.0 * factory_width
        strip_rows = (
            factory_top + 0.38 * factory_height,
            factory_top + 0.62 * factory_height,
        )
        if self.camera_position is not None:
            position_x, position_y = self.camera_position
            has_position = True
        else:
            # The sandbox represents visual tracking only. Never substitute
            # the serial coordinates when the camera has not acquired a block.
            position_x, position_y = 30, 15
            has_position = False
        point_x = factory_left + position_x / 60.0 * factory_width
        point_y = factory_bottom - position_y / 30.0 * factory_height
        for start, end in (
            ((factory_left, factory_top), (factory_right, factory_top)),
            ((factory_right, factory_top), (factory_right, factory_bottom)),
            ((factory_right, factory_bottom), (factory_left, factory_bottom)),
            ((factory_left, factory_bottom), (factory_left, factory_top)),
        ):
            self._reference_line(*start, *end, "#F4F6FA", 4)

        lamp_index = physical_x_to_lamp_index(position_x)
        for row_y in strip_rows:
            self._reference_line(strip_left, row_y, strip_right, row_y, "#52677E", 2)
            for index in range(30):
                bead_x = strip_left + index / 29.0 * (strip_right - strip_left)
                if not has_position:
                    colour = "#20D6A5"
                elif index == lamp_index:
                    colour = "#FF4248"
                elif abs(index - lamp_index) <= 2:
                    colour = "#FFB51B"
                else:
                    colour = "#20D6A5"
                self._reference_oval(
                    bead_x - 2.7, row_y - 2.7,
                    bead_x + 2.7, row_y + 2.7,
                    colour,
                )

        self._reference_line(point_x, factory_top, point_x, factory_bottom, "#C7CDD5", 2, dash=(7, 6))
        if has_position:
            x, y = position_x, position_y
            self._reference_oval(point_x - 12, point_y - 12, point_x + 12, point_y + 12, "#3185FF")
            label_y = point_y + 28 if point_y < factory_bottom - 35 else point_y - 25
            self._reference_text("position", point_x, label_y, f"重物（{x}cm，{y}cm）", "#FF4248", 8, "center")
            self._reference_text(
                "lamp-position", 606, 520,
                f"灯珠坐标 {lamp_index}/29 ｜ 有效灯带 X=5–55cm",
                "#FFFFFF", 8, "center",
            )
        else:
            self._reference_text("position", 606, 520, "等待摄像头识别重物位置", "#FF4248", 8, "center")
        # Existing text items survive between frames while masks are recreated;
        # raise them after every redraw so no value is hidden by a later mask.
        canvas.tag_raise("live-text")

    def _button(self, master: tk.Misc, text: str, command, secondary: bool = False) -> tk.Button:
        return tk.Button(
            master, text=text, command=command, cursor="hand2", relief="flat", bd=0,
            bg=PANEL if secondary else BLUE_2, fg=INK if secondary else "white",
            activebackground=BLUE_SOFT if secondary else BLUE,
            activeforeground=INK if secondary else "white",
            padx=16, pady=8, font=("song ti", 10, "bold"),
            highlightbackground=BORDER, highlightthickness=1 if secondary else 0,
        )

    def _status_tile(self, master: tk.Misc, title: str, row: int, column: int, accent: str) -> tk.Label:
        tile = tk.Frame(master, bg=BLUE_SOFT, highlightbackground=BORDER, highlightthickness=1)
        tile.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
        tk.Frame(tile, bg=accent, height=3).pack(fill="x", padx=9, pady=(8, 0))
        tk.Label(tile, text=title, bg=BLUE_SOFT, fg=MUTED,
                 font=("song ti", 10, "bold")).pack(anchor="w", padx=12, pady=(7, 1))
        value = tk.Label(tile, text="--", bg=BLUE_SOFT, fg=accent,
                         font=("DejaVu Sans", 18, "bold"))
        value.pack(anchor="w", padx=12, pady=(0, 10))
        return value

    def refresh_clock(self) -> None:
        self.clock_label.config(text=datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        if self.serial_port and self.last_frame_at and time.monotonic() - self.last_frame_at > 3.0:
            self.port_status.config(text="串口在线，等待数据", fg=AMBER)
            self.header_status.config(text="● 数据暂时中断", fg="#FFE0A8")
            self.light_card.set_stale()
            self.temp_card.set_stale()
        self.after(1000, self.refresh_clock)

    def refresh_ports(self) -> None:
        current = self.port_combo.get()
        ports = list(list_ports.comports())
        labels = [f"{port.device}  |  {port.description}" for port in ports]
        self.port_combo["values"] = labels
        if current in labels:
            self.port_combo.set(current)
        elif labels:
            preferred = next((label for label in labels if label.startswith("/dev/ttyUSB0")), labels[0])
            self.port_combo.set(preferred)
            self.port_status.config(text="已识别串口", fg=BLUE)
        else:
            self.port_combo.set("")
            self.port_status.config(text="未发现串口", fg=RED)

    def selected_device(self) -> str:
        return self.port_combo.get().split("  |  ", 1)[0].strip()

    def auto_connect(self) -> None:
        if not self.demo and self.serial_port is None and self.selected_device():
            self.connect_serial()

    def maintain_serial_connection(self) -> None:
        """Prefer the CH340 sensor adapter whenever it reappears."""
        if not self.demo:
            self.refresh_ports()
            labels = tuple(self.port_combo["values"])
            usb_label = next((label for label in labels if label.startswith("/dev/ttyUSB0")), "")
            if usb_label and self.current_port != "/dev/ttyUSB0":
                if self.serial_port is not None:
                    self.disconnect_serial("切换到传感器串口")
                self.port_combo.set(usb_label)
                self.connect_serial()
            elif self.serial_port is None:
                self.auto_connect()
        self.after(2000, self.maintain_serial_connection)

    def toggle_serial(self) -> None:
        if self.serial_port:
            self.disconnect_serial("串口已断开")
        else:
            self.connect_serial()

    def connect_serial(self) -> None:
        device = self.selected_device()
        if not device:
            self.port_status.config(text="请选择串口", fg=RED)
            return
        try:
            self.serial_port = serial.Serial(
                device, SERIAL_BAUD, timeout=0, write_timeout=0.25
            )
            self.serial_port.reset_input_buffer()
        except (OSError, serial.SerialException) as exc:
            self.serial_port = None
            self.port_status.config(text="连接失败", fg=RED)
            self.footer_status.config(text=f"无法打开 {device}: {exc}")
            return
        self.current_port = device
        self.serial_buffer = ""
        self.connect_button.config(text="断开串口", bg="#EAF2FF", fg=BLUE)
        self.port_status.config(text=f"在线 · {SERIAL_BAUD} 8N1", fg=GREEN)
        self.header_status.config(text=f"● 串口已连接 {device}", fg="#C9FFE8")
        self.footer_status.config(text=f"正在接收 {device}，等待首帧数据")
        self.last_sent_lamp_position = None
        self.pending_lamp_position = None
        self.pending_lamp_frames = 0
        self.send_camera_position(force=True)

    def disconnect_serial(self, reason: str) -> None:
        if self.serial_port:
            try:
                self.serial_port.close()
            except serial.SerialException:
                pass
        self.serial_port = None
        self.last_sent_lamp_position = None
        self.pending_lamp_position = None
        self.pending_lamp_frames = 0
        self.connect_button.config(text="连接串口", bg=BLUE_2, fg="white")
        self.port_status.config(text=reason, fg=MUTED)
        self.header_status.config(text="● 串口未连接", fg="#DCEBFF")

    def poll_serial(self) -> None:
        if self.serial_port:
            try:
                waiting = self.serial_port.in_waiting
                if waiting:
                    chunk = self.serial_port.read(min(waiting, 4096))
                    self.serial_buffer += chunk.decode("utf-8", errors="ignore").replace("\r", "\n")
                    while "\n" in self.serial_buffer:
                        line, self.serial_buffer = self.serial_buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            self.handle_line(line)
            except (OSError, serial.SerialException) as exc:
                self.footer_status.config(text=f"串口读取失败: {exc}")
                self.disconnect_serial("连接异常")
        self.after(SERIAL_POLL_MS, self.poll_serial)

    def poll_tcp_events(self) -> None:
        try:
            while True:
                event = self.tcp_server.events.get_nowait()
                if event[0] == "connected":
                    self.cloud_value.config(text=f"云端 ● 已连接 {event[1]}", fg=GREEN)
                elif event[0] == "disconnected":
                    self.cloud_value.config(text=f"云端 ● 等待 TCP {TCP_PORT}", fg=AMBER)
                elif event[0] == "listening":
                    self.cloud_value.config(text=f"云端 ● 等待 TCP {event[1]}", fg=AMBER)
                elif event[0] == "error":
                    self.cloud_value.config(text="云端 ● 监听异常", fg=RED)
                    self.footer_status.config(text=f"TCP {TCP_PORT} 监听失败: {event[1]}")
        except queue.Empty:
            pass
        self.after(100, self.poll_tcp_events)

    def send_best_alarm_frequency(self, frequency_hz: float) -> bool:
        """Send the latest best frequency through the dashboard serial port."""
        if self.serial_port is None:
            self.footer_status.config(
                text=f"最佳频率 {frequency_hz:.0f} Hz · 串口未连接，未发送"
            )
            return False

        try:
            payload = write_beep_command(self.serial_port, frequency_hz)
        except (OSError, ValueError, serial.SerialException) as exc:
            self.footer_status.config(text=f"蜂鸣指令发送失败: {exc}")
            self.disconnect_serial("蜂鸣指令发送失败")
            return False

        self.footer_status.config(text=f"已发送 {payload.decode('utf-8')}")
        return True

    def poll_noise_events(self) -> None:
        try:
            while True:
                event = self.noise_monitor.events.get_nowait()
                status = event.get("status")
                if status == "ok":
                    frequency_hz = float(event["best_alarm_hz"])
                    self.max_noise_frequency.config(text=f"{float(event['max_noise_hz']):.0f} Hz")
                    self.best_alarm_frequency.config(text=f"{frequency_hz:.0f} Hz")
                    sent = self.send_best_alarm_frequency(frequency_hz)
                    self.noise_status.config(
                        text=(
                            f"自动采集并发送 · {datetime.now().strftime('%H:%M:%S')}"
                            if sent
                            else f"自动采集 · 等待串口 · {datetime.now().strftime('%H:%M:%S')}"
                        ),
                        fg=GREEN if sent else AMBER,
                    )
                elif status == "no_input":
                    self.noise_status.config(text="无音频输入 · 保持上次结果", fg=AMBER)
                elif status == "starting":
                    self.noise_status.config(text="正在采集 0.8 秒音频…", fg=AMBER)
                elif status == "worker_error":
                    self.noise_status.config(text="采集进程异常 · 等待重启", fg=RED)
        except queue.Empty:
            pass
        self.after(200, self.poll_noise_events)

    def maintain_noise_monitor(self) -> None:
        if not self.noise_monitor.is_running():
            self.noise_monitor.start()
        self.after(4000, self.maintain_noise_monitor)

    def handle_line(self, line: str) -> None:
        frame = parse_sensor_line(line)
        if frame:
            # Forward only complete, CRLF-delimited sensor frames.  TCP reads
            # can split or combine serial chunks, so forwarding raw chunks can
            # leave web clients with unusable partial messages.
            payload = (line + "\r\n").encode("utf-8")
            self.tcp_server.cache_latest(payload)
            self.tcp_server.send(payload)
            self.latest_line.config(text=line, fg=INK)
            self.apply_frame(frame)

    def apply_frame(self, frame: Optional[SensorFrame]) -> None:
        if frame is None:
            return
        now = time.monotonic()
        previous_frame_at = self.last_frame_at
        if self.packet_count == 0:
            self.first_packet_at = now
        self.packet_count += 1
        self.last_frame_at = now
        self.light_card.update_value(str(frame.light), frame.light_raw, frame.light / 100.0)
        temp_level = (frame.temperature + 20.0) / 100.0
        self.temp_card.update_value(f"{frame.temperature:+.2f}", frame.temperature_raw, temp_level)
        if frame.humidity is not None:
            self.humidity_card.update_value(str(frame.humidity), "RH", frame.humidity / 100.0)
        else:
            self.humidity_card.set_stale()
        if frame.x is not None and frame.y is not None:
            self.sandbox.set_position(frame.x, frame.y)
        self.mode_value.config(text=str(frame.mode), fg=GREEN if frame.mode else MUTED)
        self.tick_value.config(text=f"{frame.tick // 1000} 秒")
        self.uptime_value.config(text=format_uptime(frame.tick))
        if previous_frame_at:
            interval = max(now - previous_frame_at, 0.001)
            self.rate_value.config(text=f"{1.0 / interval:.1f} Hz")
        else:
            self.rate_value.config(text="-- Hz")
        self.port_status.config(text=f"实时接收 · {self.packet_count} 帧", fg=GREEN)
        self.header_status.config(text=f"● 数据在线 {self.current_port or '演示'}", fg="#C9FFE8")
        self.footer_status.config(text=f"最后更新 {datetime.now().strftime('%H:%M:%S')} · 数据帧 {self.packet_count}")
        self.reference_frame = frame
        if hasattr(self, "reference_canvas"):
            self._reference_draw(frame)

    def toggle_fullscreen(self, _event=None) -> None:
        self.fullscreen = not self.fullscreen
        self.attributes("-fullscreen", self.fullscreen)

    def leave_fullscreen(self, _event=None) -> None:
        if self.fullscreen:
            self.fullscreen = False
            self.attributes("-fullscreen", False)

    def go_back(self) -> None:
        """Return to the desktop while keeping the monitoring process alive."""
        if self.fullscreen:
            self.fullscreen = False
            self.attributes("-fullscreen", False)
        self.after_idle(self.iconify)

    def close(self) -> None:
        self.noise_monitor.stop()
        self.camera_panel.stop()
        self.tcp_server.stop()
        if self.serial_port:
            self.serial_port.close()
        self.destroy()


def self_test() -> int:
    sample = "tick=256002 mode=1 light=93% raw=308 temp=+41.41C raw=994 humidity=50% (125,125)"
    parsed = parse_sensor_line(sample)
    expected = SensorFrame(256002, 1, 93, 308, 41.41, 994, 50, 125, 125)
    if parsed != expected:
        print(f"SELF_TEST_FAILED parsed={parsed!r}", file=sys.stderr)
        return 1
    legacy = parse_sensor_line("tick=1 mode=0 light=2% raw=3 temp=-4.05C raw=6")
    lower = parse_sensor_line("tick=1 mode=0 light=2% raw=3 temp=-4.05C raw=6 humidity=7% (0,0)")
    upper = parse_sensor_line("tick=1 mode=0 light=2% raw=3 temp=-4.05C raw=6 humidity=7% (249,249)")
    if (legacy is None or legacy.humidity is not None or legacy.x is not None or
            lower is None or (lower.x, lower.y) != (0, 0) or
            upper is None or (upper.x, upper.y) != (249, 249)):
        print(f"SELF_TEST_FAILED legacy={legacy!r}", file=sys.stderr)
        return 1
    danger_cases = {
        5: False, 6: True, 8: True, 10: True, 11: False, None: False,
    }
    if any(lamp_index_is_dangerous(value) != expected
           for value, expected in danger_cases.items()):
        print("SELF_TEST_FAILED danger zone bounds", file=sys.stderr)
        return 1
    print(f"SELF_TEST_OK {parsed}; bounds=(0,0)..(249,249); legacy_compatible=True")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--demo", action="store_true", help="显示示例帧，不自动连接串口")
    parser.add_argument("--self-test", action="store_true", help="只测试串口解析器")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    app = Dashboard(demo=args.demo)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
