# STM32 应用层 / STM32 Application Layer

## 中文

`APP` 是 CubeMX 生成层之上的业务代码：

| 模块 | 职责 |
| --- | --- |
| `scheduler.*` | 基于 `HAL_GetTick()` 的协作式周期调度 |
| `app_tasks.*` | 按键、坐标、蜂鸣器、传感器封装与 LED 心跳 |
| `bsp_system.*` | 系统共享状态 |
| `sensor_app.*` | 光敏和 MCU 内部温度采集 |
| `dht_app.*` | TIM2 + EXTI 驱动的 DHT11 非阻塞状态机 |
| `uart_app.*` | USART1 环形缓冲、命令解析与周期状态上报 |
| `ws2812_app.*` | PC7/PC8 两路 WS2812 GRB 数据输出 |

启动路径为 `main()` → `schedule_init()` → 循环调用 `schedule_run()`。DHT11
最短采样间隔为 1 秒；有效温湿度保存在 `dht_temp` 和 `dht_hum`。USART1
接收二进制 `0x01`～`0x04` 控制命令，并支持文本命令 `beep:XXXX`。

`RBCC_STM32总体架构图.png` 给出模块关系。修改调度周期或共享状态时应同步检查
串口输出、上位机解析和硬件时序。

## English

`APP` contains the business logic above the CubeMX-generated layer. It provides
a `HAL_GetTick()` cooperative scheduler, key and actuator tasks, shared state,
light/internal-temperature sensing, a TIM2+EXTI non-blocking DHT11 driver,
USART1 buffering and commands, and dual WS2812 output.

Startup follows `main()` → `schedule_init()` → repeated `schedule_run()`.
DHT11 samples are spaced by at least one second. USART1 accepts binary commands
`0x01` through `0x04` and the text command `beep:XXXX`. When changing task
periods or shared state, recheck serial output, host parsing, and hardware timing.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
