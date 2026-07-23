# RBCC 龙门起重机智能监测与控制系统

[English](#english) | [中文](#中文)

## 中文

RBCC 是一套面向龙门起重机教学与原型验证的软硬件协同系统。项目以
STM32F407 为现场控制核心，以 Orange Pi/Linux 为监控与分析平台，组合了环境
传感、灯带与蜂鸣器控制、串口/TCP 通信、视觉检测、自适应噪声警告和浏览器
调试终端。

### 项目组成

| 目录 | 说明 |
| --- | --- |
| [`RBCC_STM32/`](RBCC_STM32/) | STM32F407 固件、CubeMX 配置和 Keil 工程 |
| [`linux_code/`](linux_code/) | Orange Pi/Linux 监控界面、视觉与噪声模块 |
| [`tcp连接测试_html/`](tcp连接测试_html/) | 浏览器端 TCP 数据调试终端及 Node.js 桥接服务 |
| [`里程碑报告/`](里程碑报告/) | 项目阶段报告和演示视频 |

### 系统数据流

```text
传感器/按键/灯带/蜂鸣器
          ↕
      STM32F407
          ↕ USART
Orange Pi 监控界面 ── TCP :8888 ── HTML 调试终端
     ↙           ↘
视觉检测          噪声分析与警告音
```

### 快速开始

1. 固件：使用 STM32CubeMX 打开 `RBCC_STM32/RBCC_STM32.ioc`，或使用
   Keil MDK-ARM 打开 `RBCC_STM32/MDK-ARM/RBCC_STM32.uvprojx`。
2. Linux 监控端：进入 `linux_code/RBCC_Interface` 后运行 `./run.sh`。
3. TCP 调试端：安装 Node.js，进入 `tcp连接测试_html` 后运行
   `node server.js`，再访问 <http://127.0.0.1:3000>。
4. 各模块的依赖、参数和验证方法见对应目录 README。

### 使用边界

本项目用于教学、研究和原型验证，不是经过认证的工业安全系统。真实现场部署
前必须独立验证电气安全、机械限位、通信失效保护、告警声压、误报漏报和紧急
停机链路。

## English

RBCC is a hardware-software system for gantry-crane education and prototype
validation. An STM32F407 handles field control while an Orange Pi/Linux host
provides monitoring and analysis. The repository combines environmental
sensing, LED-strip and buzzer control, serial/TCP communication, computer
vision, adaptive noise alarms, and a browser-based TCP diagnostic terminal.

### Repository layout

| Directory | Purpose |
| --- | --- |
| [`RBCC_STM32/`](RBCC_STM32/) | STM32F407 firmware, CubeMX configuration, and Keil project |
| [`linux_code/`](linux_code/) | Orange Pi/Linux dashboard, vision, and noise modules |
| [`tcp连接测试_html/`](tcp连接测试_html/) | Browser TCP terminal and local Node.js bridge |
| [`里程碑报告/`](里程碑报告/) | Milestone reports and demonstration video |

### Quick start

1. Firmware: open `RBCC_STM32/RBCC_STM32.ioc` in STM32CubeMX or
   `RBCC_STM32/MDK-ARM/RBCC_STM32.uvprojx` in Keil MDK-ARM.
2. Linux dashboard: run `./run.sh` from `linux_code/RBCC_Interface`.
3. TCP terminal: install Node.js, run `node server.js` from
   `tcp连接测试_html`, and open <http://127.0.0.1:3000>.
4. See each module README for dependencies, parameters, and validation steps.

### Safety scope

This repository is intended for education, research, and prototyping. It is not
a certified industrial safety system. Electrical safety, mechanical limits,
fail-safe communications, alarm sound pressure, detection accuracy, and the
emergency-stop chain must be validated independently before field deployment.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
