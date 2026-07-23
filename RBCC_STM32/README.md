# RBCC STM32F407 固件 / RBCC STM32F407 Firmware

## 中文

本工程面向正点原子探索者 STM32F407 开发板，主控为 STM32F407ZGT6。底层由
STM32CubeMX/HAL 配置，应用层使用无 RTOS 的协作式轮询调度器，Keil 工程使用
MDK-ARM/ARMCC5。

### 主要功能

- 四按键扫描、坐标控制与 LED 心跳；
- 两路 WS2812 灯带；
- ADC 光敏采样与芯片内部温度采样；
- PG15 上的 DHT11 非阻塞状态机（外接 4.7 kΩ～10 kΩ 上拉至 3.3 V）；
- PA6/TIM3 PWM 蜂鸣器及 PF8 GPIO 蜂鸣器；
- USART1 `115200 8N1` 状态上报与命令接收。

### 工程入口

| 文件/目录 | 说明 |
| --- | --- |
| `RBCC_STM32.ioc` | STM32CubeMX 工程 |
| `Core/` | CubeMX 生成的启动、外设和中断代码 |
| `APP/` | 调度器与业务模块 |
| `Drivers/` | STM32 HAL 与 CMSIS |
| `MDK-ARM/RBCC_STM32.uvprojx` | Keil MDK-ARM 工程 |

用 CubeMX 重新生成代码前，请先核对 `APP` 文件组、头文件路径和引脚归属。
尤其注意 PC8 在历史配置中同时涉及 HUB75_OE 与第二路 WS2812；必须明确唯一
用途后再生成。编译成功不等于传感器和执行器已经通过真实硬件验证。

## English

This firmware targets the ALIENTEK Explorer STM32F407 board with an
STM32F407ZGT6 MCU. STM32CubeMX/HAL provides the low-level configuration, while
the application uses a cooperative polling scheduler without an RTOS. The Keil
project targets MDK-ARM/ARMCC5.

Features include four keys and coordinate control, dual WS2812 strips, light
and internal-temperature ADC sampling, a non-blocking DHT11 state machine on
PG15, PWM/GPIO buzzers, and USART1 at `115200 8N1`.

Before regenerating CubeMX code, verify the `APP` source group, include paths,
and pin ownership. PC8 has historically been assigned both HUB75_OE and the
second WS2812 output; choose one purpose before regeneration. A successful
build does not prove operation on real sensors and actuators.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
