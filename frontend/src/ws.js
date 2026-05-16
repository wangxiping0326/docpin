// WebSocket 客户端 - 长连接管理
let sock = null;
let listeners = [];
let reconnectTimer = null;
let reconnCount = 0;

function getWsUrl() {
  const loc = window.location;
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  return proto + '//' + loc.host + '/ws';
}

export function connectWS() {
  const tok = localStorage.getItem('docpin_tok');
  if (!tok) return;

  const url = getWsUrl();
  sock = new WebSocket(url);

  sock.onopen = () => {
    reconnCount = 0;
    // 先发 token 认证
    sock.send(JSON.stringify({ type: 'auth', token: tok }));
    console.log('[WS] 连上了');
  };

  sock.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      // 通知所有 listener
      listeners.forEach(fn => fn(data));
    } catch (e) {
      // ignore
    }
  };

  sock.onclose = () => {
    console.log('[WS] 断开，自动重连...');
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnCount++;
    const delay = Math.min(5000, reconnCount * 1000);
    reconnectTimer = setTimeout(() => connectWS(), delay);
  };

  sock.onerror = () => {
    // onclose 会处理
  };
}

export function addWSListener(fn) {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter(f => f !== fn);
  };
}

export function sendWSMsg(msg) {
  if (sock && sock.readyState === WebSocket.OPEN) {
    sock.send(JSON.stringify(msg));
  }
}

export function closeWS() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (sock) sock.close();
}
