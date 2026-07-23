const http = require('node:http');
const net = require('node:net');
const fs = require('node:fs');
const path = require('node:path');

const WEB_HOST = '127.0.0.1';
const WEB_PORT = Number(process.env.WEB_PORT || 3000);
const ROOT = __dirname;

let tcpSocket = null;
let status = 'disconnected';
let activeTarget = { host: '10.16.137.132', port: 8888 };
const eventClients = new Set();
let receiveBuffer = Buffer.alloc(0);

const staticFiles = {
  '/': ['index.html', 'text/html; charset=utf-8'],
  '/index.html': ['index.html', 'text/html; charset=utf-8'],
  '/styles.css': ['styles.css', 'text/css; charset=utf-8'],
  '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
};

function emit(type, payload = {}) {
  const packet = `data: ${JSON.stringify({ type, ...payload })}\n\n`;
  for (const response of eventClients) response.write(packet);
}

function setStatus(nextStatus, detail = '') {
  status = nextStatus;
  emit('status', { status, detail, target: activeTarget });
}

function closeTcpSocket() {
  const socket = tcpSocket;
  tcpSocket = null;
  if (socket && !socket.destroyed) socket.destroy();
}

function emitFrame(frame, timestamp = new Date().toISOString()) {
  // 设备使用 CRLF 分帧。这里仅在拿到完整一行后才交给页面，
  // 避免 TCP 拆包导致同一帧显示成多条记录。
  emit('data', {
    text: frame.toString('utf8'),
    hex: frame.toString('hex').match(/.{1,2}/g)?.join(' ') || '',
    bytes: frame.length,
    timestamp,
    completeFrame: true,
  });
}

function consumeTcpData(chunk) {
  receiveBuffer = Buffer.concat([receiveBuffer, chunk]);

  let newlineIndex = receiveBuffer.indexOf(0x0a);
  while (newlineIndex !== -1) {
    let frame = receiveBuffer.subarray(0, newlineIndex);
    receiveBuffer = receiveBuffer.subarray(newlineIndex + 1);

    if (frame.length > 0 && frame[frame.length - 1] === 0x0d) {
      frame = frame.subarray(0, frame.length - 1);
    }
    if (frame.length > 0) emitFrame(frame);

    newlineIndex = receiveBuffer.indexOf(0x0a);
  }

  // 防止异常设备长期不发送换行导致内存持续增长。
  if (receiveBuffer.length > 1024 * 1024) {
    emit('log', { level: 'error', message: '接收缓存超过 1 MB，已清空；请检查设备帧结束符' });
    receiveBuffer = Buffer.alloc(0);
  }
}

function connectTcp(host, port) {
  closeTcpSocket();
  receiveBuffer = Buffer.alloc(0);
  activeTarget = { host, port };
  setStatus('connecting', `正在连接 ${host}:${port}`);

  const socket = new net.Socket();
  tcpSocket = socket;
  socket.setNoDelay(true);
  socket.setKeepAlive(true, 10_000);
  socket.setTimeout(10_000);

  socket.connect(port, host, () => {
    if (tcpSocket !== socket) return;
    socket.setTimeout(0);
    setStatus('connected', `TCP 握手成功，已连接 ${host}:${port}`);
  });

  socket.on('data', (buffer) => {
    if (tcpSocket !== socket) return;
    consumeTcpData(buffer);
  });

  socket.on('timeout', () => {
    if (tcpSocket !== socket) return;
    setStatus('error', '连接超时（10 秒）');
    socket.destroy();
  });

  socket.on('error', (error) => {
    if (tcpSocket !== socket) return;
    setStatus('error', `网络错误：${error.message}`);
  });

  socket.on('close', () => {
    if (tcpSocket !== socket) return;
    if (receiveBuffer.length > 0) {
      emit('log', {
        level: 'error',
        message: `连接关闭时仍有 ${receiveBuffer.length} 字节不完整帧，未显示`,
      });
      receiveBuffer = Buffer.alloc(0);
    }
    tcpSocket = null;
    setStatus('disconnected', 'TCP 连接已关闭');
  });
}

function json(response, code, body) {
  response.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  response.end(JSON.stringify(body));
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    let raw = '';
    request.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > 1024 * 1024) reject(new Error('请求内容过大'));
    });
    request.on('end', () => {
      try { resolve(raw ? JSON.parse(raw) : {}); }
      catch { reject(new Error('JSON 格式无效')); }
    });
    request.on('error', reject);
  });
}

function validHost(host) {
  return typeof host === 'string' && host.trim().length > 0 && host.length <= 253;
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host || WEB_HOST}`);

  if (request.method === 'GET' && url.pathname === '/api/events') {
    response.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    });
    eventClients.add(response);
    response.write(`data: ${JSON.stringify({ type: 'status', status, target: activeTarget })}\n\n`);
    request.on('close', () => eventClients.delete(response));
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/state') {
    json(response, 200, { status, target: activeTarget });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/connect') {
    try {
      const body = await readJson(request);
      const host = String(body.host || '').trim();
      const port = Number(body.port);
      if (!validHost(host) || !Number.isInteger(port) || port < 1 || port > 65535) {
        json(response, 400, { ok: false, error: 'IP/主机名或端口无效' });
        return;
      }
      connectTcp(host, port);
      json(response, 202, { ok: true });
    } catch (error) {
      json(response, 400, { ok: false, error: error.message });
    }
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/disconnect') {
    closeTcpSocket();
    setStatus('disconnected', '已主动断开连接');
    json(response, 200, { ok: true });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/send') {
    try {
      const body = await readJson(request);
      const message = typeof body.message === 'string' ? body.message : '';
      if (!tcpSocket || tcpSocket.destroyed || status !== 'connected') {
        json(response, 409, { ok: false, error: 'TCP 尚未连接' });
        return;
      }
      if (!message) {
        json(response, 400, { ok: false, error: '发送内容不能为空' });
        return;
      }
      tcpSocket.write(Buffer.from(message, 'utf8'), (error) => {
        if (error) emit('log', { level: 'error', message: `发送失败：${error.message}` });
      });
      emit('sent', { text: message, bytes: Buffer.byteLength(message, 'utf8'), timestamp: new Date().toISOString() });
      json(response, 200, { ok: true });
    } catch (error) {
      json(response, 400, { ok: false, error: error.message });
    }
    return;
  }

  const entry = staticFiles[url.pathname];
  if (request.method === 'GET' && entry) {
    const [fileName, contentType] = entry;
    fs.readFile(path.join(ROOT, fileName), (error, content) => {
      if (error) {
        json(response, 500, { error: '页面文件读取失败' });
        return;
      }
      response.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-store' });
      response.end(content);
    });
    return;
  }

  json(response, 404, { error: 'Not found' });
});

server.listen(WEB_PORT, WEB_HOST, () => {
  console.log(`TCP HTML 客户端已启动：http://${WEB_HOST}:${WEB_PORT}`);
  console.log(`默认 TCP 目标：${activeTarget.host}:${activeTarget.port}`);
});

function shutdown() {
  closeTcpSocket();
  for (const response of eventClients) response.end();
  server.close(() => process.exit(0));
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
