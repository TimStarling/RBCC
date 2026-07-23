# TCP HTML 数据接收终端 / TCP HTML Data Terminal

## 中文

浏览器不能直接访问原生 TCP Socket，因此 `server.js` 在本机提供 HTTP/SSE
桥接，并连接目标 TCP 服务。控制页仅监听 `127.0.0.1:3000`。默认目标为
`10.16.137.132:8888`，可在网页中调整。

功能包括连接状态、UTF-8/HEX 显示、发送文本、断开重连和清空日志。
接收端使用缓冲区按 `\r\n` 提取完整帧，正确处理 TCP 拆包和粘包；发送内容
直接编码为 UTF-8，不自动追加换行。

### 运行

安装 Node.js 后双击 `start.bat`，或执行：

```powershell
node server.js
```

然后访问 <http://127.0.0.1:3000>。预期结果是本地页面显示桥接状态；只有目标
主机可达且 `8888` 端口服务运行时，设备连接才会成功。

## English

Browsers cannot open native TCP sockets, so `server.js` provides a local
HTTP/SSE bridge and connects to the target TCP service. The control page listens
only on `127.0.0.1:3000`. The default target is `10.16.137.132:8888` and can be
changed in the page.

The terminal shows connection state, UTF-8 and hexadecimal payloads, sends
text, reconnects, and clears logs. Incoming bytes are buffered and split on
`\r\n`, so TCP fragmentation and coalescing are handled correctly. Outgoing
text is UTF-8 without an automatically appended newline.

Install Node.js, run `node server.js`, and open <http://127.0.0.1:3000>. A live
device connection additionally requires the target host and port to be reachable.

## 致谢 / Acknowledgements

衷心感谢 TimStarling、学习路上的文仔、帕罗西汀、一盒小面包、Jalin、六十六
对本项目的卓越贡献。

Sincere thanks to TimStarling, 学习路上的文仔, 帕罗西汀, 一盒小面包, Jalin,
and 六十六 for their outstanding contributions to this project.
