# Qt 上位机 / Qt Host Application

## 中文

该工程是基于 Qt Widgets 的桥式起重机上位机，入口为 `222.pro`。界面通过
`QStackedWidget` 组织广告/主页、TCP 通信和智能分拣页面：

- `adwidget.*`：默认页和页面跳转；
- `tcpwidget.*`：`QTcpSocket` 连接、UTF-8 收发和状态显示；
- `sortwidget.*`：摄像头预览、抓拍和图像分类交互；
- `Sorting/`：HTTP 请求和图像编码辅助代码；
- `image/`、`image.qrc`：界面资源。

### 构建

使用支持 Qt Multimedia、Qt Network 和 C++17 的 Qt 5 工具链打开
`222.pro`，执行 qmake 后构建。工程中的 `tools/` 脚本面向历史
MinGW 7.3 32 位配置，新环境应优先使用当前 Qt Kit。

### 凭据安全

`config.h` 只保留百度云 API 占位符。请在本地填写新凭据，且不要提交真实
密钥。如果旧凭据曾被共享或上传，应立即在云平台撤销并重新生成。

当前工程包含真实 TCP 和摄像头调用，但是否可连接设备、识别图像或完成页面
流程，仍需在目标电脑和现场网络中验证。

## English

This Qt Widgets bridge-crane host application is opened through `222.pro`.
A `QStackedWidget` combines home, TCP, and intelligent-sorting pages.
`tcpwidget.*` uses `QTcpSocket`; `sortwidget.*` handles camera preview and image
capture; `Sorting/` contains HTTP and image helpers.

Build with a Qt 5 kit that provides Widgets, Network, Multimedia, and C++17.
The scripts under `tools/` target a historical 32-bit MinGW 7.3 setup; prefer a
current configured Qt Kit on a new workstation.

`config.h` contains placeholders only. Configure new cloud API credentials
locally and never commit real secrets. Device connectivity, cloud recognition,
and the complete page flow require validation in the target environment.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
