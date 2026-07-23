from __future__ import annotations

import sys
import types
from pathlib import Path


INTERFACE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTERFACE_DIR))

# The test venv contains pytest but not pyserial. Stub only the import surface
# needed to load main.py; the tests use RecordingSerial below.
serial_module = types.ModuleType("serial")
serial_tools_module = types.ModuleType("serial.tools")


class SerialException(Exception):
    pass


serial_module.Serial = object
serial_module.SerialException = SerialException
serial_tools_module.list_ports = types.SimpleNamespace(comports=lambda: [])
serial_module.tools = serial_tools_module
sys.modules.setdefault("serial", serial_module)
sys.modules.setdefault("serial.tools", serial_tools_module)

import main  # noqa: E402


class RecordingSerial:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []
        self.flush_count = 0

    def write(self, payload: bytes) -> int:
        self.payloads.append(payload)
        return len(payload)

    def flush(self) -> None:
        self.flush_count += 1


class RecordingLabel:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def config(self, **kwargs: object) -> None:
        self.options.update(kwargs)


class DashboardHarness:
    def __init__(self, serial_port: RecordingSerial | None) -> None:
        self.serial_port = serial_port
        self.footer_status = RecordingLabel()
        self.disconnected_reason: str | None = None

    def disconnect_serial(self, reason: str) -> None:
        self.disconnected_reason = reason
        self.serial_port = None


def test_dashboard_sends_best_frequency_when_serial_is_connected() -> None:
    port = RecordingSerial()
    dashboard = DashboardHarness(port)

    sent = main.Dashboard.send_best_alarm_frequency(dashboard, 3000)

    assert sent is True
    assert port.payloads == [b"beep:3000"]
    assert port.flush_count == 1
    assert dashboard.footer_status.options["text"] == "已发送 beep:3000"
    assert dashboard.disconnected_reason is None


def test_dashboard_skips_send_when_serial_is_disconnected() -> None:
    dashboard = DashboardHarness(None)

    sent = main.Dashboard.send_best_alarm_frequency(dashboard, 3000)

    assert sent is False
    assert dashboard.footer_status.options["text"] == "最佳频率 3000 Hz · 串口未连接，未发送"
    assert dashboard.disconnected_reason is None
