# 噪声模块测试 / Noise Module Tests

## 中文

本目录覆盖配置校验、音频输入、噪声分析、频率选择、警告音生成、结果导出和
命令行入口。从 `linux_code/RBCC_Noise` 运行：

```bash
python -m pytest -q
```

自动测试不包含真实麦克风、扬声器声压和厂房声场验证。

## English

These tests cover configuration validation, audio input, noise analysis,
frequency selection, alarm synthesis, result export, and the CLI. Run
`python -m pytest -q` from `linux_code/RBCC_Noise`. Automated tests do not
validate a real microphone, speaker sound pressure, or factory acoustics.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
