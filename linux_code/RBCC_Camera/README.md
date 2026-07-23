# RBCC 视觉检测 / RBCC Vision Detection

## 中文

`white_object_detector.py` 使用 OpenCV 读取摄像头画面，在已知的白色厂区边框
内检测红色重物和黄色作业人员，并将结果换算为物理坐标。默认摄像头为 Linux
稳定设备路径，实际部署前应通过 `--help` 查看并按现场设备调整参数。

### 依赖与运行

```bash
python3 -m pip install opencv-python numpy
python3 white_object_detector.py --help
python3 white_object_detector.py
```

监控界面通常通过 `RBCC_Interface/camera_worker.py` 启动本模块，并通过共享
内存传递 640×360 RGB 画面和检测结果。`*.backup*`、`*.before_*`、日志、
`kernel_meta/` 与 `__pycache__/` 是本地历史或运行产物，不属于发布源码。

## English

`white_object_detector.py` uses OpenCV to capture camera frames, detect red
loads and yellow workers inside a known white factory boundary, and convert
detections to physical coordinates. The default camera is a stable Linux device
path; inspect `--help` and calibrate it for the deployment site.

The dashboard normally starts this module through
`RBCC_Interface/camera_worker.py`. Frames and detections are exchanged through
shared memory as 640×360 RGB data. Backup files, logs, `kernel_meta/`, and
Python caches are local history or runtime artifacts rather than release source.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
