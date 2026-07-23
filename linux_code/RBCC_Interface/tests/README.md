# 监控平台测试 / Dashboard Tests

## 中文

本目录验证自动蜂鸣协议、监控界面联动和噪声采样周期。请从
`linux_code/RBCC_Interface` 运行：

```bash
python3 -m pytest -q
```

测试主要覆盖纯逻辑和组件协作，不能替代真实串口、摄像头、蓝牙音频与显示器
的整机测试。

## English

These tests cover the automatic buzzer protocol, dashboard integration, and
noise-capture cadence. Run `python3 -m pytest -q` from
`linux_code/RBCC_Interface`. Logic and component tests do not replace
end-to-end validation with the real serial device, camera, Bluetooth audio, and
display.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
