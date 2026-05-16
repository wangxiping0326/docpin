// 顶栏导航 - 菜单 + 用户信息
import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Menu, Dropdown, Button, Space } from 'antd';
import {
  DashboardOutlined, ExperimentOutlined, AlertOutlined,
  DatabaseOutlined, ToolOutlined, SettingOutlined,
  UserOutlined, TeamOutlined, DownOutlined, LogoutOutlined
} from '@ant-design/icons';

const menuItems = [
  { key: '/dash', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/shot', icon: <ExperimentOutlined />, label: '注射控制' },
  { key: '/alarm', icon: <AlertOutlined />, label: '报警监控' },
  { key: '/data', icon: <DatabaseOutlined />, label: '用药数据' },
  { key: '/device', icon: <ToolOutlined />, label: '设备管理' },
];

export default function TopBar({ me, onLogout }) {
  const nav = useNavigate();
  const loc = useLocation();
  const [cur, setCur] = useState(loc.pathname);

  const userMenu = {
    items: [
      me?.role === 'admin' ? { key: 'users', icon: <TeamOutlined />, label: '用户管理' } : null,
      me?.role === 'admin' ? { key: 'settings', icon: <SettingOutlined />, label: '系统设置' } : null,
      { type: 'divider' },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出', danger: true },
    ].filter(Boolean),
    onClick: ({ key }) => {
      if (key === 'logout') onLogout();
      else if (key === 'users') { nav('/users'); setCur(key); }
      else if (key === 'settings') { nav('/settings'); setCur(key); }
    }
  };

  const handleMenu = ({ key }) => { nav(key); setCur(key); };

  return (
    <div className="topbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        <h3>💉 高精度智能电子注射器管控系统</h3>
        <Menu
          theme="dark" mode="horizontal"
          selectedKeys={[cur === '/' ? '/dash' : cur]}
          items={menuItems}
          onClick={handleMenu}
          style={{ flex: 1, minWidth: 400 }}
        />
      </div>
      <div className="right-part">
        <Dropdown menu={userMenu}>
          <Button type="text" style={{ color: '#fff' }}>
            <Space>
              <UserOutlined /> {me?.username || '?'} ({me?.role === 'admin' ? '管理员' : '操作员'})
              <DownOutlined />
            </Space>
          </Button>
        </Dropdown>
      </div>
    </div>
  );
}
