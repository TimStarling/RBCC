# Noise Capture Cadence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the RBCC dashboard capture 0.8 seconds of audio on a fixed 4.5-second start-to-start cadence.

**Architecture:** Keep the existing long-lived `noise_worker.py` process. Measure each cycle with `time.monotonic()`, perform capture and analysis synchronously, then interruptibly wait only for the remainder of the 4.5-second period; do not overlap slow cycles. Keep the dashboard watchdog independent and update only its visible capture-duration text.

**Tech Stack:** Python 3.10, `threading.Event`, `time.monotonic`, pytest, existing RBCC Noise virtual environment.

## Global Constraints

- Audio capture duration is exactly `0.8` seconds.
- Normal start-to-start update interval is exactly `4.5` seconds.
- Slow cycles never overlap; when elapsed time is at least 4.5 seconds, the next cycle starts immediately.
- Error cycles use the same 4.5-second rate limit.
- SIGTERM and SIGINT remain interruptible during both capture and waiting.
- Noise analysis, frequency scoring, serial behavior, and the 4-second process-health watchdog do not change.
- The remote RBCC tree is not a Git repository. Do not initialize one without user authorization; use SHA-256 file hashes as checkpoints instead of commit steps.

---

### Task 1: Worker timing contract and fixed cadence

**Files:**
- Create: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_noise_worker_timing.py`
- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/noise_worker.py:1-90`

**Interfaces:**
- Consumes: existing `AlarmConfig`, `capture_microphone`, `analyze_noise`, `select_warning_frequencies`, and module-level `stop_event`.
- Produces: `CAPTURE_DURATION_SECONDS: float`, `UPDATE_INTERVAL_SECONDS: float`, and `remaining_cycle_seconds(cycle_started: float, now: float | None = None) -> float`.

- [ ] **Step 1: Write the failing timing tests**

Create `tests/test_noise_worker_timing.py` with this complete content:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest


INTERFACE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTERFACE_DIR))

import noise_worker  # noqa: E402


def test_capture_and_update_constants() -> None:
    assert noise_worker.CAPTURE_DURATION_SECONDS == pytest.approx(0.8)
    assert noise_worker.UPDATE_INTERVAL_SECONDS == pytest.approx(4.5)


def test_remaining_cycle_seconds_uses_period_remainder() -> None:
    remaining = noise_worker.remaining_cycle_seconds(10.0, now=10.8)
    assert remaining == pytest.approx(3.7)


def test_remaining_cycle_seconds_never_returns_negative() -> None:
    remaining = noise_worker.remaining_cycle_seconds(10.0, now=14.7)
    assert remaining == 0.0
```

- [ ] **Step 2: Run the timing tests and verify the red state**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q tests/test_noise_worker_timing.py
```

Expected: FAIL because `CAPTURE_DURATION_SECONDS`, `UPDATE_INTERVAL_SECONDS`, and `remaining_cycle_seconds` do not exist.

- [ ] **Step 3: Add the timing constants and pure wait calculation**

In `noise_worker.py`, change the module docstring and add the constants after `NOISE_PROJECT_DIR`:

```python
"""Capture 0.8-second noise samples on a fixed 4.5-second cadence."""

NOISE_PROJECT_DIR = Path("/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise")
CAPTURE_DURATION_SECONDS = 0.8
UPDATE_INTERVAL_SECONDS = 4.5
```

Add this function immediately after `emit`:

```python
def remaining_cycle_seconds(cycle_started: float, now: float | None = None) -> float:
    """Return the interruptible wait needed to preserve the fixed cadence."""
    current = time.monotonic() if now is None else now
    elapsed = current - cycle_started
    return max(0.0, UPDATE_INTERVAL_SECONDS - elapsed)
```

- [ ] **Step 4: Apply the constants to the worker loop**

Replace the configuration and loop timing portion of `main()` with this structure while keeping the existing capture, analysis, selection, and emitted payload fields unchanged:

```python
def main() -> int:
    signal.signal(signal.SIGTERM, lambda *_args: stop_event.set())
    signal.signal(signal.SIGINT, lambda *_args: stop_event.set())
    config = AlarmConfig(
        sample_rate=16000,
        analysis_duration=CAPTURE_DURATION_SECONDS,
    )
    previous: tuple[float, ...] | None = None

    while not stop_event.is_set():
        cycle_started = time.monotonic()
        try:
            devices = list_input_devices()
            if not devices:
                raise RuntimeError("没有检测到音频输入设备")
            device = int(devices[0]["index"])
            audio = capture_microphone(
                config.analysis_duration,
                config.sample_rate,
                device=device,
                stop_event=stop_event,
            )
            if stop_event.is_set():
                break
            if audio.size == 0:
                raise RuntimeError("没有采集到音频样本")

            analysis = analyze_noise(audio, config.sample_rate, config)
            selection = select_warning_frequencies(analysis, config, previous)
            previous = selection.frequencies_hz
            emit(
                {
                    "status": "ok",
                    "max_noise_hz": strongest_noise_frequency(analysis),
                    "best_alarm_hz": float(selection.choices[0].frequency_hz),
                    "noise_type": analysis.noise_type,
                    "device": str(devices[0]["name"]),
                    "captured_at": time.time(),
                }
            )
        except Exception as error:
            emit({"status": "no_input", "message": str(error), "captured_at": time.time()})

        stop_event.wait(remaining_cycle_seconds(cycle_started))
    return 0
```

This removes the old `stop_event.wait(2.0)` from only the exception path and gives normal and error cycles the same fixed cadence.

- [ ] **Step 5: Run the timing tests and verify the green state**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q tests/test_noise_worker_timing.py
```

Expected: `3 passed`.

- [ ] **Step 6: Record a Task 1 checkpoint**

Run:

```bash
sha256sum /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/noise_worker.py \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_noise_worker_timing.py
```

Expected: two SHA-256 hashes. Preserve them in the implementation log; no Git commit is possible in this project.

---

### Task 2: Dashboard copy and runtime cadence verification

**Files:**
- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_noise_worker_timing.py`
- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/main.py:1208-1220`

**Interfaces:**
- Consumes: `CAPTURE_DURATION_SECONDS = 0.8` and the worker's JSON-lines output.
- Produces: dashboard startup text `正在采集 0.8 秒音频…` and runtime evidence of approximately 4.5-second update intervals.

- [ ] **Step 1: Add a failing dashboard-copy test**

Append this test to `tests/test_noise_worker_timing.py`:

```python
def test_dashboard_copy_matches_capture_duration() -> None:
    source = (INTERFACE_DIR / "main.py").read_text(encoding="utf-8")
    assert "正在采集 0.8 秒音频…" in source
    assert "正在采集 2 秒音频…" not in source
```

- [ ] **Step 2: Run the new test and verify the red state**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q \
  tests/test_noise_worker_timing.py::test_dashboard_copy_matches_capture_duration
```

Expected: FAIL because `main.py` still contains `正在采集 2 秒音频…`.

- [ ] **Step 3: Update the dashboard startup text**

In `main.py`, replace only this branch:

```python
elif status == "starting":
    self.noise_status.config(text="正在采集 0.8 秒音频…", fg=AMBER)
```

Do not change `self.after(4000, self.maintain_noise_monitor)`; it is a health check, not the sampling cadence.

- [ ] **Step 4: Run the interface timing tests**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python -m pytest -q tests/test_noise_worker_timing.py
```

Expected: `4 passed`.

- [ ] **Step 5: Run the existing noise-analysis regression suite**

Run:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Noise
.venv/bin/python -m pytest -q
```

Expected: all existing tests pass with zero failures.

- [ ] **Step 6: Measure three real worker updates**

Run this harness from `RBCC_Interface`; it starts the real worker, collects three successful JSON events, terminates it, and verifies both intervals:

```bash
cd /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface
python3 - <<'PY'
import json
import subprocess
import time

process = subprocess.Popen(
    [
        "/home/HwHiAiUser/Desktop/RBCC/RBCC_Noise/.venv/bin/python",
        "noise_worker.py",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
events = []
deadline = time.monotonic() + 12.0
try:
    while len(events) < 3 and time.monotonic() < deadline:
        line = process.stdout.readline()
        if not line:
            break
        event = json.loads(line)
        if event.get("status") == "ok":
            events.append(event)
finally:
    process.terminate()
    process.wait(timeout=3.0)

assert len(events) == 3, events
intervals = [
    events[index]["captured_at"] - events[index - 1]["captured_at"]
    for index in range(1, len(events))
]
assert all(4.3 <= interval <= 4.7 for interval in intervals), intervals
print(f"CAPTURED_EVENTS={len(events)}")
print("UPDATE_INTERVALS=" + ",".join(f"{value:.6f}" for value in intervals))
PY
```

Expected: `CAPTURED_EVENTS=3` and two measured intervals between `4.3` and `4.7` seconds. A zero-RMS PulseAudio source is acceptable for this cadence test because audio quality is outside this change.

- [ ] **Step 7: Check source text and record the final checkpoint**

Run:

```bash
rg -n "0\.8|4\.5|采集 2 秒" \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/noise_worker.py \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/main.py
sha256sum \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/noise_worker.py \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/main.py \
  /home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/tests/test_noise_worker_timing.py
```

Expected: the new `0.8` and `4.5` values appear, the old UI phrase does not appear, and three final SHA-256 hashes are recorded. No commit step is run because the remote project has no Git repository.
