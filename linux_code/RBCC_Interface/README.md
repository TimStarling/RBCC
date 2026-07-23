# RBCC 龙门起重机环境监测平台 / RBCC Gantry-Crane Monitoring Platform

## 中文

该应用是 Orange Pi 上的主监控界面，面向 1920×1080 固定显示屏，整合：

- STM32 串口状态：`115200 8N1`，自动发现并重连 CH340；
- `0.0.0.0:8888` TCP 服务和完整 `\r\n` 数据帧转发；
- 光照、DHT11 温湿度、坐标、模式和蜂鸣器状态；
- `camera_worker.py` 视觉共享内存画面与检测结果；
- `noise_worker.py` 周期采音、频谱分析和自适应警告音；
- 危险区域灯光提示与 `beep:XXXX` 串口频率控制。

### 安装与运行

```bash
sudo apt install -y python3-tk python3-serial python3-opencv python3-pil.imagetk
python3 -m pip install -r requirements.txt
chmod +x run.sh
./run.sh
```

解析器自检：

```bash
python3 main.py --self-test
```

桌面启动文件为 `RBCC_Interface.desktop`。代码中的
`/home/HwHiAiUser/Desktop/RBCC`、摄像头 Python 路径、蓝牙声卡和字体名称
是当前部署值；迁移到新设备时必须同步修改并重新验证。

### 数据格式

```text
tick=256002 mode=1 light=93% raw=308 temp=+41C raw=994 humidity=50% (125,125)
```

TCP 与串口都是字节流，界面按应用协议缓存并提取完整帧，不能把单次读取当成
一条完整消息。

## English

This is the main Orange Pi dashboard for a fixed 1920×1080 display. It combines
an auto-reconnecting CH340 serial link at `115200 8N1`, a TCP service on
`0.0.0.0:8888`, sensor and position state, vision frames through shared memory,
periodic noise analysis, adaptive alarm audio, and `beep:XXXX` frequency
control.

Install the dependencies, make `run.sh` executable, and start it as shown
above. Run `python3 main.py --self-test` to check the parser. Absolute paths,
the camera Python runtime, Bluetooth card, and font name reflect the current
deployment and must be updated and revalidated on a new host.

Serial and TCP are byte streams. The application buffers data and extracts
complete protocol frames; one read callback is not assumed to equal one message.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
