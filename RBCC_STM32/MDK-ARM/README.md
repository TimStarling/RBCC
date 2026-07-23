# Keil MDK-ARM 工程 / Keil MDK-ARM Project

## 中文

使用 Keil µVision 打开 `RBCC_STM32.uvprojx`。工程目标为 STM32F407ZGTx，
现有配置使用 ARMCC 5.06 update 7。`RTE/` 和 `DebugConfig/` 保存工程配置；
目标文件、列表文件、构建日志及 `RBCC_STM32/` 输出目录是生成产物，不提交到
仓库。

命令行编译示例：

```powershell
UV4.exe -b RBCC_STM32.uvprojx -j0 -o build.log
```

预期输出为 Keil 编译结果及目标映像。下一步应烧录开发板，并分别验证串口、
DHT11、灯带、按键、ADC 与蜂鸣器；仅有零错误编译不能证明硬件工作正常。

## English

Open `RBCC_STM32.uvprojx` in Keil µVision. The target is STM32F407ZGTx and the
current toolchain is ARMCC 5.06 update 7. `RTE/` and `DebugConfig/` are project
configuration; object/list files, logs, and the `RBCC_STM32/` output directory
are generated and excluded from version control.

The command above builds the project and writes a log. After a successful
build, flash the board and validate USART, DHT11, LED strips, keys, ADC, and
buzzers individually.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
