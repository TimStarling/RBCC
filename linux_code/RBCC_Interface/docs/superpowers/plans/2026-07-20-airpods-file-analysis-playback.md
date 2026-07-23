# AirPods Capture and Serial Beep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Capture an exact 0.8-second AirPods HFP microphone WAV every 4.5 seconds, select one 2000–5000 Hz model frequency, and send UTF-8 `beep:XXXX` over the existing serial port without headphone playback.

**Files:**

- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/noise_worker.py`
- Modify: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/main.py`
- Runtime output: `/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/runtime/environment_audio/latest.wav`

## Tasks

- [x] Switch the known AirPods card to `handsfree_head_unit` and discover `bluez_source.*`.
- [x] Record nominal 0.8-second Pulse input with ffmpeg, normalize to exactly 12800 mono 16 kHz samples, and overwrite `latest.wav`.
- [x] Analyze the saved WAV and emit one `best_alarm_hz` in the inclusive 2000–5000 Hz range.
- [x] Remove all `generate_alarm`, `paplay`, and headphone playback behavior.
- [x] Restore strict `encode_beep_command()` and `write_beep_command()` in the current GUI version.
- [x] Call serial sending from each successful noise event; write exactly nine UTF-8 bytes and flush.
- [x] Run Python syntax checks only, then perform one real capture and serial write.
- [x] Restart the GUI/worker using the existing `flock` single-instance launcher.

## Verified result

The live capture produced a 0.800000-second, 16 kHz mono WAV. The model selected 5000 Hz and the production writer sent `beep:5000` (`626565703a35303030`, nine bytes). The final GUI owns `/dev/ttyUSB0`; no headphone playback calls remain.
