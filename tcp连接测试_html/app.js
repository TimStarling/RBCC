const elements = {
  host: document.querySelector('#hostInput'),
  port: document.querySelector('#portInput'),
  connect: document.querySelector('#connectButton'),
  statusPill: document.querySelector('#statusPill'),
  statusText: document.querySelector('#statusText'),
  detail: document.querySelector('#connectionDetail'),
  terminal: document.querySelector('#terminal'),
  empty: document.querySelector('#emptyState'),
  counter: document.querySelector('#packetCounter'),
  clear: document.querySelector('#clearButton'),
  form: document.querySelector('#sendForm'),
  message: document.querySelector('#messageInput'),
  send: document.querySelector('#sendButton'),
};

const labels = {
  disconnected: '未连接',
  connecting: '连接中',
  connected: '已连接',
  error: '连接异常',
};

let currentStatus = 'disconnected';
let packets = 0;
let totalBytes = 0;

function timeLabel(timestamp = new Date().toISOString()) {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date(timestamp));
}

function updateCounter() {
  elements.counter.textContent = `${packets} 帧 / ${formatBytes(totalBytes)}`;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function appendLog(direction, text, meta = '', timestamp) {
  elements.empty?.remove();
  const entry = document.createElement('div');
  entry.className = `log-entry ${direction}`;

  const time = document.createElement('span');
  time.className = 'log-time';
  time.textContent = timeLabel(timestamp);

  const type = document.createElement('span');
  type.className = 'log-direction';
  type.textContent = direction === 'receive' ? 'RX' : direction === 'send' ? 'TX' : direction === 'error' ? 'ERR' : 'SYS';

  const content = document.createElement('span');
  content.className = 'log-content';
  content.textContent = text || '(空数据)';
  if (meta) {
    const details = document.createElement('small');
    details.className = 'log-meta';
    details.textContent = meta;
    content.appendChild(details);
  }

  entry.append(time, type, content);
  elements.terminal.append(entry);
  elements.terminal.scrollTop = elements.terminal.scrollHeight;
}

function renderStatus(status, detail = '', target) {
  currentStatus = status;
  const connected = status === 'connected';
  const busy = status === 'connecting';
  elements.statusPill.dataset.status = status;
  elements.statusText.textContent = labels[status] || status;
  elements.detail.textContent = detail || (connected ? 'TCP 握手成功' : '等待建立 TCP 握手');
  elements.connect.textContent = connected ? '断开连接' : busy ? '正在连接…' : '建立连接';
  elements.connect.classList.toggle('disconnect', connected);
  elements.connect.disabled = busy;
  elements.host.disabled = connected || busy;
  elements.port.disabled = connected || busy;
  elements.message.disabled = !connected;
  elements.send.disabled = !connected;
  if (target) {
    elements.host.value = target.host;
    elements.port.value = target.port;
  }
}

async function post(url, body = {}) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作失败');
  return result;
}

elements.connect.addEventListener('click', async () => {
  try {
    if (currentStatus === 'connected') {
      await post('/api/disconnect');
      return;
    }
    await post('/api/connect', { host: elements.host.value.trim(), port: Number(elements.port.value) });
  } catch (error) {
    appendLog('error', error.message);
  }
});

elements.form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = elements.message.value;
  if (!message) return;
  try {
    await post('/api/send', { message });
    elements.message.value = '';
    elements.message.focus();
  } catch (error) {
    appendLog('error', error.message);
  }
});

elements.clear.addEventListener('click', () => {
  elements.terminal.replaceChildren();
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.id = 'emptyState';
  empty.innerHTML = '<span class="pulse-ring"></span><strong>等待设备数据</strong><small>连接成功后，每个完整传输帧会实时显示在这里</small>';
  elements.terminal.append(empty);
  packets = 0;
  totalBytes = 0;
  updateCounter();
});

const events = new EventSource('/api/events');
events.onmessage = ({ data }) => {
  const event = JSON.parse(data);
  if (event.type === 'status') {
    renderStatus(event.status, event.detail, event.target);
    if (event.detail) appendLog(event.status === 'error' ? 'error' : 'system', event.detail);
  } else if (event.type === 'data') {
    packets += 1;
    totalBytes += event.bytes;
    updateCounter();
    appendLog('receive', event.text, `完整帧 · ${event.bytes} B · HEX: ${event.hex}`, event.timestamp);
  } else if (event.type === 'sent') {
    appendLog('send', event.text, `${event.bytes} B`, event.timestamp);
  } else if (event.type === 'log') {
    appendLog(event.level === 'error' ? 'error' : 'system', event.message);
  }
};

events.onerror = () => {
  elements.detail.textContent = '页面与本地桥接服务通信中断，正在重连';
};

fetch('/api/state')
  .then((response) => response.json())
  .then((state) => renderStatus(state.status, '', state.target))
  .catch((error) => appendLog('error', `初始化失败：${error.message}`));
