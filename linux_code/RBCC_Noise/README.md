# 厂房噪声感知型自适应警告器 / Adaptive Factory-Noise Alarm

## 中文

这是兼容 Windows 与 Linux/Orange Pi 的 Python 原型。程序从麦克风或 WAV
读取厂房噪声，使用 STFT、短时能量、频谱平坦度和频谱峰值进行分析，在指定
频段选择背景噪声较弱且彼此分离的警告频率，并生成警告音。

### 安装

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

Linux 还需 PortAudio 和 Tk：

```bash
sudo apt install -y python3-tk libportaudio2 portaudio19-dev
```

### 使用

```bash
python main_cli.py --list-devices
python main_cli.py --source microphone --duration 2
python main_cli.py --source file --input demo_factory_noise.wav --no-play
python main_gui.py
```

默认导出目录包含 `spectrum.png`、`noise_profile.csv`、
`analysis_result.json` 和 `generated_alarm.wav`。运行测试：

```bash
python -m pytest -q
python -m compileall .
```

本模块是算法与硬件原型，不是认证的工业告警设备。现场使用前必须验证声压级、
覆盖范围、听力保护、误报漏报、失效保护及灯光/振动冗余。

## English

This Python prototype runs on Windows and Linux/Orange Pi. It reads factory
noise from a microphone or WAV file, analyzes STFT, short-time energy, spectral
flatness, and spectral peaks, selects separated warning frequencies in quieter
bands, and synthesizes an alarm pattern.

Create a virtual environment and install `requirements.txt`. Linux also needs
PortAudio and Tk packages. Use `main_cli.py` for scripted operation or
`main_gui.py` for the Tk interface. Results include a spectrum plot, noise
profile, JSON analysis, and generated WAV alarm.

This is not a certified industrial alarm. Validate sound pressure, coverage,
hearing protection, false alarms, missed detections, fail-safe behavior, and
visual or vibration redundancy before field use.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
