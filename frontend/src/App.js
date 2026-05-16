// 主壳子 - 路由 + 全局状态
import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, message } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Login from './pages/Login';
import Dash from './pages/Dash';
import ShotControl from './pages/ShotControl';
import AlarmPage from './pages/AlarmPage';
import DataPage from './pages/DataPage';
import DevicePage from './pages/DevicePage';
import SettingPage from './pages/SettingPage';
import UserPage from './pages/UserPage';
import TopBar from './components/TopBar';
import AlarmToast from './components/AlarmToast';
import { connectWS, addWSListener } from './ws';
import './App.css';

// 全局消息 context - 懒得用 redux 了，直接挂 window
window._docpin = { shoting: false, alarmList: [] };

function App() {
  const [me, setMe] = useState(null);
  const [alarmInfo, setAlarmInfo] = useState(null);
  const [wsReady, setWsReady] = useState(false);
  const tmpX = localStorage.getItem('docpin_tok');

  useEffect(() => {
    if (tmpX) {
      // 尝试连接 ws
      connectWS();
      const rm = addWSListener((data) => {
        if (data.type === 'hello') {
          setWsReady(true);
          message.success(data.data?.msg || '连接成功');
        }
        if (data.type === 'alarm') {
          const d = data.data;
          setAlarmInfo(d);
          window._docpin.alarmList.push(d);
          // 3秒后自动消失
          setTimeout(() => setAlarmInfo(null), 5000);
        }
        if (data.type === 'notification') {
          const lvl = data.data?.level || 'info';
          if (lvl === 'warning') message.warning(data.data?.msg || '');
          else message.info(data.data?.msg || '');
        }
        if (data.type === 'progress') {
          window._docpin.shoting = data.data?.running || false;
        }
        if (data.type === 'shot_done') {
          message.success('注射完成了！');
          window._docpin.shoting = false;
        }
        if (data.type === 'shot_stopped' || data.type === 'shot_started') {
          window._docpin.shoting = data.type === 'shot_started';
        }
      });
      return () => { rm(); };
    }
  }, [tmpX]);

  // 解析 token 拿用户信息（纯前端偷懒版，不用每次都调 /me）
  useEffect(() => {
    if (!tmpX) return;
    try {
      const parts = tmpX.split('.');
      if (parts.length === 3) {
        const payload = JSON.parse(atob(parts[1]));
        setMe({ id: payload.uid, username: payload.uname, role: payload.role });
      }
    } catch (e) {
      // ignore
    }
  }, [tmpX]);

  const doLogout = useCallback(() => {
    localStorage.removeItem('docpin_tok');
    localStorage.removeItem('docpin_user');
    setMe(null);
  }, []);

  if (!me) {
    return (
      <ConfigProvider locale={zhCN}>
        <Login onLogin={(u) => { setMe(u); connectWS(); }} />
      </ConfigProvider>
    );
  }

  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <div className="app-shell">
          <TopBar me={me} onLogout={doLogout} />
          <div className="main-area">
            <Routes>
              <Route path="/" element={<Dash />} />
              <Route path="/dash" element={<Dash />} />
              <Route path="/shot" element={<ShotControl me={me} />} />
              <Route path="/alarm" element={<AlarmPage />} />
              <Route path="/data" element={<DataPage />} />
              <Route path="/device" element={<DevicePage />} />
              <Route path="/settings" element={<SettingPage me={me} />} />
              <Route path="/users" element={<UserPage me={me} />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </div>
          <AlarmToast info={alarmInfo} />
        </div>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
