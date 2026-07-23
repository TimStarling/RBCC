# Automatic Beep Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically select one best frequency from 2000–5000 Hz after every 0.8-second capture and send it as exact UTF-8 `beep:XXXX` over the dashboard's existing serial connection.

**Architecture:** Keep `noise_worker.py` responsible for automatic capture and frequency selection, but expose a testable config factory that restricts selection to one frequency in the required range. Keep serial ownership in `main.py`; encode and write each successful worker result through the already-open `serial.Serial` object so sensor reads and beep writes share one connection.

**Tech Stack:** Python 3.10, pyserial, existing RBCC Noise virtual environment, pytest, Tkinter event loop.

## Global Constraints

- Capture duration remains exactly `0.8` seconds.
- Normal capture start-to-start interval remains exactly `4.5` seconds.
- Only one highest-scoring frequency is selected.
- Selected frequency is a four-digit integer in the inclusive range `2000–5000`.
- Serial payload is exact UTF-8 `beep:XXXX`; no quotes, spaces, carriage return, or newline.
- Example: 3000 Hz is 9 bytes `b"beep:3000"`, hexadecimal `626565703a33303030`.
- Reuse `/dev/ttyUSB0` at `115200 8N1`; do not open a second serial connection in the worker.
- A disconnected or failing serial port must not stop automatic capture and calculation.
- Do not call `play_audio()` because the Orange Pi has only the `auto_null` PulseAudio sink.
- The remote project has no Git repository. Do not initialize one; create recoverable backups and record SHA-256 hashes instead of commits.

---

### Task 1: Restrict the worker to one best frequency in 2000–5000 Hz

**Files:**
- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_noise_worker_timing.py`
- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/noise_worker.py:50-61`

**Interfaces:**
- Produces: `build_alarm_config() -> AlarmConfig` with sample rate 16000, capture duration 0.8, warning range 2000–5000, and `frequency_count=1`.
- Consumes: existing `AlarmConfig` and unchanged worker loop.

- [ ] **Step 1: Add a failing worker-config test**

Append this test to `tests/test_noise_worker_timing.py`:

```python
def test_alarm_config_selects_one_four_digit_frequency() -> None:
    config = noise_worker.build_alarm_config()
    assert config.analysis_duration == pytest.approx(0.8)
    assert config.min_warning_hz == pytest.approx(2000.0)
    assert config.max_warning_hz == pytest.approx(5000.0)
    assert config.frequency_count == 1
```

- [ ] **Step 2: Run the test and verify the red state**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q \
  tests/test_noise_worker_timing.py::test_alarm_config_selects_one_four_digit_frequency
```

Expected: FAIL with `AttributeError: module 'noise_worker' has no attribute 'build_alarm_config'`.

- [ ] **Step 3: Add the config factory and use it in `main()`**

Add immediately before `main()`:

```python
def build_alarm_config() -> AlarmConfig:
    """Build the automatic single-frequency selection configuration."""
    return AlarmConfig(
        sample_rate=16000,
        analysis_duration=CAPTURE_DURATION_SECONDS,
        min_warning_hz=2000.0,
        max_warning_hz=5000.0,
        frequency_count=1,
    )
```

Replace the inline `AlarmConfig(...)` construction in `main()` with:

```python
config = build_alarm_config()
```

- [ ] **Step 4: Run all worker timing tests**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q tests/test_noise_worker_timing.py
```

Expected: `5 passed`.

- [ ] **Step 5: Record Task 1 hashes**

Run:

```bash
sha256sum \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/noise_worker.py \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_noise_worker_timing.py
```

Expected: two hashes recorded; no Git commit is possible.

---

### Task 2: Encode and write the exact UTF-8 beep protocol

**Files:**
- Create: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_auto_beep.py`
- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/main.py:5-80`

**Interfaces:**
- Produces: `encode_beep_command(frequency_hz: float) -> bytes`.
- Produces: `write_beep_command(serial_port, frequency_hz: float) -> bytes`.
- Consumes: any pyserial-compatible object implementing `write(bytes) -> int` and `flush() -> None`.

- [ ] **Step 1: Write failing protocol tests**

Create `tests/test_auto_beep.py` with this content:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest


INTERFACE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTERFACE_DIR))

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
```

- [ ] **Step 2: Run protocol tests and verify the red state**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q tests/test_auto_beep.py
```

Expected: FAIL because `encode_beep_command` and `write_beep_command` do not exist.

- [ ] **Step 3: Add protocol constants, encoder, and writer**

Add `import math` with the standard-library imports in `main.py`, then add these definitions after `SERIAL_PATTERN`:

```python
BEEP_MIN_HZ = 2000
BEEP_MAX_HZ = 5000


def encode_beep_command(frequency_hz: float) -> bytes:
    """Encode one validated four-digit beep command without a line ending."""
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
    """Write and flush one complete beep command on an existing serial port."""
    payload = encode_beep_command(frequency_hz)
    written = serial_port.write(payload)
    if written != len(payload):
        raise OSError(f"short serial write: {written}/{len(payload)} bytes")
    serial_port.flush()
    return payload
```

- [ ] **Step 4: Run protocol tests and verify the green state**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q tests/test_auto_beep.py
```

Expected: `9 passed`.

- [ ] **Step 5: Record Task 2 hashes**

Run:

```bash
sha256sum \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/main.py \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_auto_beep.py
```

Expected: two hashes recorded; no Git commit is possible.

---

### Task 3: Send every successful automatic result through the shared serial port

**Files:**
- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_auto_beep.py`
- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/main.py:1229-1248`

**Interfaces:**
- Produces: `Dashboard.send_best_alarm_frequency(frequency_hz: float) -> bool`.
- Consumes: `write_beep_command(self.serial_port, frequency_hz)` and existing `disconnect_serial(reason)`.

- [ ] **Step 1: Add failing dashboard send tests**

Append these test doubles and tests to `tests/test_auto_beep.py`:

```python
class RecordingLabel:
    def __init__(self) -> None:
        self.values: list[dict[str, object]] = []

    def config(self, **kwargs: object) -> None:
        self.values.append(kwargs)


class DashboardHarness:
    send_best_alarm_frequency = main.Dashboard.send_best_alarm_frequency

    def __init__(self, serial_port) -> None:
        self.serial_port = serial_port
        self.footer_status = RecordingLabel()
        self.disconnect_reasons: list[str] = []

    def disconnect_serial(self, reason: str) -> None:
        self.disconnect_reasons.append(reason)
        self.serial_port = None


def test_dashboard_sends_best_frequency_on_connected_port() -> None:
    port = RecordingSerial()
    dashboard = DashboardHarness(port)
    assert dashboard.send_best_alarm_frequency(3000) is True
    assert port.payloads == [b"beep:3000"]
    assert dashboard.disconnect_reasons == []


def test_dashboard_skips_send_when_serial_is_disconnected() -> None:
    dashboard = DashboardHarness(None)
    assert dashboard.send_best_alarm_frequency(3000) is False
    assert dashboard.disconnect_reasons == []
    assert "未发送" in str(dashboard.footer_status.values[-1]["text"])
```

- [ ] **Step 2: Run dashboard send tests and verify the red state**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q \
  tests/test_auto_beep.py::test_dashboard_sends_best_frequency_on_connected_port \
  tests/test_auto_beep.py::test_dashboard_skips_send_when_serial_is_disconnected
```

Expected: test collection FAILS because `Dashboard.send_best_alarm_frequency` does not exist.

- [ ] **Step 3: Add the dashboard send method**

Add this method immediately before `poll_noise_events()`:

```python
def send_best_alarm_frequency(self, frequency_hz: float) -> bool:
    """Send one automatic beep command without interrupting noise analysis."""
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
```

- [ ] **Step 4: Call the method for every successful worker event**

In the `status == "ok"` branch of `poll_noise_events()`, store the frequency once, display it, send it, and update the status:

```python
frequency_hz = float(event["best_alarm_hz"])
self.max_noise_frequency.config(text=f"{float(event['max_noise_hz']):.0f} Hz")
self.best_alarm_frequency.config(text=f"{frequency_hz:.0f} Hz")
sent = self.send_best_alarm_frequency(frequency_hz)
self.noise_status.config(
    text=(
        f"自动采集并播放 · {datetime.now().strftime('%H:%M:%S')}"
        if sent
        else f"自动采集 · 等待串口 · {datetime.now().strftime('%H:%M:%S')}"
    ),
    fg=GREEN if sent else AMBER,
)
```

- [ ] **Step 5: Run all interface tests**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q tests
```

Expected: `16 passed` (`5` timing tests and `11` automatic beep tests).

- [ ] **Step 6: Run regression and compile checks**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m py_compile main.py noise_worker.py
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Noise
.venv/bin/python -m pytest -q
```

Expected: compilation succeeds and all existing 26 tests pass.

- [ ] **Step 7: Perform one controlled real serial write**

First verify `/dev/ttyUSB0` is not held by another process. If free, open it at 115200 8N1 and call the production `write_beep_command()` with a validated best frequency. Assert and print the payload, hexadecimal representation, and `9/9` bytes written. If the dashboard owns the port, do not open a competing connection; launch or observe one automatic result through the dashboard instead.

Expected for 3000 Hz:

```text
PAYLOAD=beep:3000
UTF8_HEX=626565703a33303030
BYTES_WRITTEN=9/9
```

- [ ] **Step 8: Record final hashes and preserve backups**

Run:

```bash
sha256sum \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/noise_worker.py \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/main.py \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_noise_worker_timing.py \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_auto_beep.py
```

Expected: four final hashes recorded. Preserve the existing `.before_cadence_0p8_4p5_20260720` backups and create new non-overwriting pre-auto-beep backups before editing active files.
