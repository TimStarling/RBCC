# ARM64 离线多媒体依赖 / ARM64 Offline Multimedia Dependencies

## 中文

本目录保存 2026-07-20 为 Ubuntu 22.04 ARM64 环境收集的 `.deb` 包，主要覆盖
GStreamer、MPV、图像格式、音频编解码和相关运行库。它们用于目标机无法联网
时的离线部署，不应在其他 Ubuntu 版本或 CPU 架构上直接混用。

安装前先确认目标系统：

```bash
dpkg --print-architecture
lsb_release -rs
```

在本目录中可使用 `sudo apt install ./*.deb` 让 APT 处理包关系。安装后应分别
验证音视频播放、摄像头和应用实际需要的编解码器。

## English

This directory contains `.deb` packages collected on 2026-07-20 for Ubuntu
22.04 ARM64. They cover GStreamer, MPV, image formats, audio codecs, and
supporting runtime libraries for offline deployment.

Confirm the target architecture and Ubuntu release before installation. Do not
mix these packages with another CPU architecture or distribution release.
From this directory, `sudo apt install ./*.deb` lets APT resolve package
relationships. Validate playback, camera input, and required codecs afterward.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
