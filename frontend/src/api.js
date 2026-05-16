// 封装 fetch 请求 - 带 token
const BASE = '';

function getToken() {
  return localStorage.getItem('docpin_tok') || '';
}

async function req(method, path, body) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + getToken(),
  };
  const opts = { method, headers };
  if (body && method !== 'GET') {
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, opts);
  if (res.status === 401) {
    localStorage.removeItem('docpin_tok');
    localStorage.removeItem('docpin_user');
    window.location.href = '/login';
    throw new Error('未登录');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '请求失败' }));
    throw new Error(err.detail || '出错了');
  }
  // 如果是导出文件，返回 blob
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('ms-excel') || ct.includes('csv')) {
    return res.blob();
  }
  return res.json();
}

const api = {
  login: (u, p) => req('POST', '/api/login', { username: u, password: p }),
  getMe: () => req('GET', '/api/me'),
  // 注射
  startShot: (d) => req('POST', '/api/shot/start', d),
  stopShot: () => req('POST', '/api/shot/stop'),
  shotStatus: () => req('GET', '/api/shot/status'),
  shotHistory: (p) => {
    const q = new URLSearchParams(p).toString();
    return req('GET', '/api/shot/history?' + q);
  },
  recommend: () => req('GET', '/api/shot/recommend'),
  // 报警
  alarms: (p) => {
    const q = new URLSearchParams(p).toString();
    return req('GET', '/api/alarm/list?' + q);
  },
  alarmStats: () => req('GET', '/api/alarm/stats'),
  getThresholds: () => req('GET', '/api/alarm/thresholds'),
  setThresholds: (d) => req('PUT', '/api/alarm/thresholds', d),
  // 设备
  devStatus: () => req('GET', '/api/device/status'),
  devPorts: () => req('GET', '/api/device/ports'),
  regDevice: (d) => req('POST', '/api/device/register', d),
  connectDev: (uid) => req('POST', '/api/device/connect', { uid }),
  disconnDev: (uid) => req('POST', '/api/device/disconnect', { uid }),
  // 统计
  doseStats: (p) => {
    const q = new URLSearchParams(p).toString();
    return req('GET', '/api/stats/dose?' + q);
  },
  exportExcel: (p) => {
    const q = new URLSearchParams(p).toString();
    return req('GET', '/api/stats/export?' + q);
  },
  opLogs: (p) => {
    const q = new URLSearchParams(p).toString();
    return req('GET', '/api/stats/logs?' + q);
  },
  // 通用 GET
  get: (path) => req('GET', path),
  // 概览
  overview: () => req('GET', '/api/stats/overview'),
  modeStats: () => req('GET', '/api/stats/mode_stats'),
  alarmTrend: () => req('GET', '/api/stats/alarm_trend'),
  dailySummary: (d) => {
    const q = new URLSearchParams(d).toString();
    return req('GET', '/api/stats/daily_summary?' + q);
  },
  cleanLogs: (d) => req('POST', '/api/stats/logs/clean', d),
  // 通用的
  del: (path) => req('DELETE', path),
  // 用户管理
  listUsers: () => req('GET', '/api/users'),
  addUser: (d) => req('POST', '/api/users', d),
  delUser: (id) => req('DELETE', '/api/users/' + id),
  delDevice: (uid) => req('DELETE', '/api/device/' + uid),
};

export default api;
