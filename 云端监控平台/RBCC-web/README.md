# RBCC Web 发布快照 / RBCC Web Release Snapshot

## 中文

本目录保存 RBCC 云端监控 Web 项目的配置、依赖锁文件、演示资料和预构建静态
页面。界面展示温度、湿度、噪声和起重机状态等信息。

### 当前文件状态

- `dist/`：已构建的静态站点快照；
- `tcp.mp4`：TCP 功能演示；
- `rbcc-document-site.zip`：项目文档站离线包；
- `package.json`、`pnpm-lock.yaml`：Vue 3、Vite、Pinia 和 ECharts 依赖配置；
- 缺少 `src/` 与 `server/tcp-bridge.mjs`。

由于源码和桥接入口不完整，`pnpm build`、`pnpm start` 和 `pnpm dev` 当前不能
作为可复现流程使用。请补回对应版本的 `src/`、`server/` 和测试源码后，再按
以下顺序验证：

```bash
corepack enable
pnpm install --frozen-lockfile
pnpm run type-check
pnpm run test:unit
pnpm run build
pnpm start
```

现有静态快照可直接预览：

```bash
cd dist
python3 -m http.server 8080
```

浏览器访问 <http://127.0.0.1:8080>。静态预览不会连接原生 TCP。浏览器如需
读取 `10.16.137.132:8888`，必须恢复 Node 桥接服务，并按 CRLF 缓冲解析完整
数据帧。

## English

This directory contains configuration, the dependency lockfile, demonstration
materials, and a prebuilt static snapshot of the RBCC cloud-monitoring Web
project. The dashboard presents temperature, humidity, noise, and crane state.

The current snapshot does not include `src/` or `server/tcp-bridge.mjs`.
Consequently, `pnpm build`, `pnpm start`, and `pnpm dev` are not reproducible
from the supplied files. Restore matching `src/`, `server/`, and test sources
before running the documented pnpm validation sequence.

Serve `dist/` with a static HTTP server for UI-only preview. Browsers cannot
connect directly to raw TCP; live access to `10.16.137.132:8888` requires the
missing Node bridge and complete CRLF-delimited frame parsing.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
