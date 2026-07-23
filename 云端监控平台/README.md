# RBCC 云端监控平台 / RBCC Cloud Monitoring Platform

## 中文

本目录汇集 RBCC 的 Web 发布快照、Qt 上位机源码和云端界面设计资料，用于
桥式起重机监控界面的演示、通信调试和后续产品化设计。

| 内容 | 说明 |
| --- | --- |
| `RBCC-web/` | Vue/Vite 项目配置、预构建 `dist` 快照、TCP 演示视频和文档站压缩包 |
| `qt上位机/` | Qt Widgets 上位机源码，包含 TCP、摄像头和图像分类页面 |
| `默认页.svg`、PNG 文件 | 云端监控默认页及厂房视觉素材 |
| `默认页制作prd.docx` | 默认页产品需求与制作说明 |
| `RBCC前端设置/` | 前端设置资料占位目录 |

### 当前可用范围

- `RBCC-web/dist/` 是现有静态发布快照，可使用任意静态 HTTP 服务预览。
- 当前材料未包含 Vue `src/` 和 `server/tcp-bridge.mjs`，因此不能从现有内容
  重新构建 Web 应用，也不能启动 `package.json` 中声明的 TCP 网关。
- Qt 工程可通过 `qt上位机/222.pro` 打开，但云端图像接口凭据已安全替换为
  占位符；启用前需在本地配置新凭据。
- TCP 地址、摄像头、云端 API 和现场数据均需在目标环境重新验证。

### 预览 Web 快照

```bash
cd RBCC-web/dist
python3 -m http.server 8080
```

然后访问 <http://127.0.0.1:8080>。这只预览静态界面，不会恢复缺失的 TCP
桥接服务。

## English

This directory collects the RBCC Web release snapshot, Qt host-application
source, and cloud-interface design assets for bridge-crane monitoring demos,
communication diagnostics, and further product development.

`RBCC-web/dist/` is a prebuilt static snapshot that can be served by any static
HTTP server. The supplied materials do not contain the Vue `src/` tree or
`server/tcp-bridge.mjs`, so the Web application cannot currently be rebuilt and
the TCP gateway declared in `package.json` cannot be started.

Open `qt上位机/222.pro` for the Qt Widgets application. Cloud-image API
credentials are represented by safe placeholders and must be configured
locally. Revalidate TCP endpoints, cameras, cloud APIs, and live field data in
the target environment.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
