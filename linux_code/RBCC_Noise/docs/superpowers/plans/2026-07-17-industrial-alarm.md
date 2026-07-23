# Industrial Adaptive Alarm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows- and Raspberry-Pi-compatible Python application that analyzes microphone or WAV factory noise, outputs three best warning frequencies, generates and optionally plays a short-short-long alarm, and exports analysis artifacts.

**Architecture:** Separate pure numerical core modules from optional audio hardware and UI modules. The analyzer converts audio into STFT-derived features, the selector scores candidate frequencies against the measured spectrum, and the generator synthesizes a clipped-safe multi-tone alarm. CLI and Tkinter GUI consume the same core APIs.

**Tech Stack:** Python 3.10+, NumPy, SciPy, Matplotlib, sounddevice (optional at import time), Tkinter, pytest.

## Global Constraints

- Support Windows and Raspberry Pi with one codebase.
- Support microphone input and WAV-file input.
- Provide both CLI and Tkinter GUI.
- Default analysis sample rate is 16000 Hz.
- Candidate warning range is 800–4000 Hz, capped below Nyquist.
- Return three frequencies separated by at least 350 Hz where possible and never less than 200 Hz.
- Do not use SVM, reinforcement learning, or deep learning in version 1.
- Use a fixed short-short-long rhythm and adaptive multi-tone carriers.
- Core tests must run without audio hardware.
- Export spectrum PNG, profile CSV, result JSON, and generated alarm WAV.

---

## File Map

- `config.py`: immutable configuration dataclass and validation.
- `models.py`: typed result dataclasses shared by modules.
- `noise_analyzer.py`: STFT features, peak detection, clipping and noise classification.
- `frequency_selector.py`: candidate scoring and separated top-frequency selection.
- `alarm_generator.py`: short-short-long synthesis, fades, limiting, playback and WAV save.
- `audio_input.py`: device enumeration, microphone capture, WAV loading and resampling.
- `result_exporter.py`: timestamped artifact export.
- `main_cli.py`: command-line application.
- `main_gui.py`: Tkinter application with embedded spectrum plot.
- `requirements.txt`: runtime and test dependencies.
- `README.md`: installation and use on Windows and Raspberry Pi.
- `tests/`: unit and integration tests using synthetic audio.

### Task 1: Configuration and Models

**Files:**
- Create: `config.py`
- Create: `models.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `AlarmConfig.validate() -> None`
- Produces: `NoiseAnalysis`, `FrequencyChoice`, `SelectionResult`, `ExportResult`

- [ ] Write tests that invalid sampling rates, frequency ranges, and spacing raise `ValueError`, and defaults validate.
- [ ] Run `pytest tests/test_config.py -v` and verify import failure.
- [ ] Implement dataclasses and exact validation rules.
- [ ] Run the test and verify all cases pass.
- [ ] Commit `feat: add alarm configuration and models`.

### Task 2: STFT Noise Analysis

**Files:**
- Create: `noise_analyzer.py`
- Test: `tests/test_noise_analyzer.py`

**Interfaces:**
- Consumes: `AlarmConfig`
- Produces: `analyze_noise(audio: np.ndarray, sample_rate: int, config: AlarmConfig) -> NoiseAnalysis`

- [ ] Write failing tests for low-level input, a 1000 Hz tonal signal, transient impulses, finite spectrum output, and clipping detection.
- [ ] Run the focused test file and verify failures are caused by missing analyzer code.
- [ ] Implement mono conversion, finite-value validation, optional resampling, STFT power, mean dB spectrum, RMS, short-time-energy statistics, spectral flatness, peak detection, and rule-based classification.
- [ ] Run the focused tests and full suite.
- [ ] Commit `feat: analyze factory noise with STFT`.

### Task 3: Best Warning Frequency Selection

**Files:**
- Create: `frequency_selector.py`
- Test: `tests/test_frequency_selector.py`

**Interfaces:**
- Consumes: `NoiseAnalysis`, `AlarmConfig`, optional previous frequencies.
- Produces: `select_warning_frequencies(analysis, config, previous_frequencies=None) -> SelectionResult`

- [ ] Write failing tests proving a strong 1000 Hz tone is avoided, multiple peaks are avoided, three choices are returned, spacing is respected, and repeated input is deterministic.
- [ ] Run focused tests and verify missing implementation failures.
- [ ] Implement candidate generation, local-band noise energy, normalized inverse-energy score, peak-distance score, mid-band hearing preference, optional stability score, hard peak exclusion, and greedy spacing selection with controlled fallback.
- [ ] Run focused tests and full suite.
- [ ] Commit `feat: select adaptive warning frequencies`.

### Task 4: Alarm Synthesis and Audio I/O

**Files:**
- Create: `alarm_generator.py`
- Create: `audio_input.py`
- Test: `tests/test_alarm_generator.py`
- Test: `tests/test_audio_input.py`

**Interfaces:**
- Produces: `generate_alarm(frequencies, config, volume=None) -> np.ndarray`
- Produces: `play_audio(audio, sample_rate) -> None`
- Produces: `save_wav(path, audio, sample_rate) -> Path`
- Produces: `load_wav(path, target_sample_rate) -> tuple[np.ndarray, int]`
- Produces: `capture_microphone(duration, sample_rate, device=None, stop_event=None) -> np.ndarray`
- Produces: `list_input_devices() -> list[dict]`

- [ ] Write failing tests for rhythm duration, finite samples, no clipping, audible carrier energy, stereo WAV conversion, and resampling.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement synthesis with attack/release fades and peak limiting; implement optional sounddevice import, helpful hardware errors, WAV conversion and polyphase resampling.
- [ ] Run focused tests and full suite.
- [ ] Commit `feat: add alarm synthesis and audio input`.

### Task 5: Export and CLI

**Files:**
- Create: `result_exporter.py`
- Create: `main_cli.py`
- Test: `tests/test_result_exporter.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `export_results(...) -> ExportResult`
- Produces: `main_cli.main(argv: Sequence[str] | None = None) -> int`

- [ ] Write failing tests that all four output files are generated with required JSON keys and that file-mode CLI completes without playback.
- [ ] Run focused tests and verify failures.
- [ ] Implement headless-safe Matplotlib plotting, CSV/JSON/WAV export, CLI parsing, device listing, microphone/file paths, result printing, optional playback and export.
- [ ] Run focused tests and full suite.
- [ ] Commit `feat: add exports and command line interface`.

### Task 6: Tkinter GUI and Documentation

**Files:**
- Create: `main_gui.py`
- Create: `requirements.txt`
- Create: `README.md`
- Test: `tests/test_imports.py`

**Interfaces:**
- Produces: `AlarmApp(root: tkinter.Tk)` and `main_gui.main() -> None`

- [ ] Write a failing import smoke test for every module without creating a GUI root or touching audio hardware.
- [ ] Run the smoke test and verify failure for the missing GUI.
- [ ] Implement a Tkinter GUI with source selection, device/file controls, duration and volume, start/stop, auto-play, save, status labels, results table, background worker and embedded spectrum plot.
- [ ] Add dependency pins/floors and platform installation/run instructions, including Raspberry Pi PortAudio packages.
- [ ] Run import test, full unit suite, compile check, and CLI help command.
- [ ] Commit `feat: add graphical interface and documentation`.

### Task 7: Verification and Distribution

**Files:**
- Create: `demo_factory_noise.py`
- Create: `industrial_alarm_code.zip` outside the repository after verification.

- [ ] Add a synthetic factory-noise generator that creates tonal, low-frequency, broadband and transient components for demonstrations.
- [ ] Run `python demo_factory_noise.py` and analyze its WAV through the CLI without playback.
- [ ] Run `pytest -q`, `python -m compileall .`, and CLI/GUI import smoke checks.
- [ ] Check git status and inspect generated output files.
- [ ] Create a ZIP excluding `.git`, `.worktrees`, caches, and generated output.
- [ ] Record verification evidence in the final response and link the project ZIP and key source files.
