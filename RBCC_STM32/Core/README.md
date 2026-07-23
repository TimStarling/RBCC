# CubeMX 核心代码 / CubeMX Core Code

## 中文

本目录由 STM32CubeMX 管理。`Src/main.c` 是固件入口，其他文件负责 GPIO、
ADC、定时器、USART、中断和系统初始化；`Inc/` 保存对应声明。业务逻辑应优先
放在 `../APP/`，手工修改生成文件时只能写在 CubeMX 保留的 `USER CODE` 区域。

## English

STM32CubeMX manages this directory. `Src/main.c` is the firmware entry point;
the remaining files configure GPIO, ADC, timers, USART, interrupts, and the
system. `Inc/` contains declarations. Prefer placing business logic in
`../APP/`, and keep manual edits to CubeMX-preserved `USER CODE` sections.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
