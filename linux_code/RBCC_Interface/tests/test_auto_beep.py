from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


INTERFACE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTERFACE_DIR))

# The test venv contains pytest but not pyserial. Stub only the import surface
# needed to load main.py; these tests use RecordingSerial below.
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
    def __init__(self, written: int | None = None) -> None:
        self.payloads: list[bytes] = []
        self.flush_count = 0
        self.written = written

    def write(self, payload: bytes) -> int:
        self.payloads.append(payload)
        return len(payload) if self.written is None else self.written

    def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.parametrize(
    ("frequency", "expected"),
    [(2000, b"beep:2000"), (3000, b"beep:3000"), (5000, b"beep:5000")],
)
def test_encode_beep_command(frequency: int, expected: bytes) -> None:
    assert main.encode_beep_command(frequency) == expected


@pytest.mark.parametrize("frequency", [1999, 5001, float("nan"), float("inf")])
def test_encode_beep_command_rejects_invalid_frequency(frequency: float) -> None:
    with pytest.raises(ValueError):
        main.encode_beep_command(frequency)


def test_write_beep_command_writes_all_bytes_and_flushes() -> None:
    port = RecordingSerial()
    payload = main.write_beep_command(port, 3000)
    assert payload == b"beep:3000"
    assert port.payloads == [b"beep:3000"]
    assert port.flush_count == 1


def test_write_beep_command_rejects_short_write() -> None:
    port = RecordingSerial(written=8)
    with pytest.raises(OSError, match="short serial write"):
        main.write_beep_command(port, 3000)
    assert port.flush_count == 0
