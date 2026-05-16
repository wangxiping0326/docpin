// 登录页 - 简单表单
import React, { useState } from 'react';
import { Card, Form, Input, Button, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import api from '../api';

export default function Login({ onLogin }) {
  const [loading, setLoading] = useState(false);

  const doLogin = async (vals) => {
    setLoading(true);
    try {
      const res = await api.login(vals.username, vals.password);
      localStorage.setItem('docpin_tok', res.token);
      localStorage.setItem('docpin_user', JSON.stringify(res.user));
      message.success('登录成功，欢迎 ' + res.user.username);
      onLogin(res.user);
    } catch (e) {
      message.error(e.message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card title="高精度智能电子注射器管控系统" style={{ width: 380, boxShadow: '0 2px 12px rgba(0,0,0,.1)' }}>
        <Form onFinish={doLogin} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '输用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '输密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
          <div style={{ color: '#999', fontSize: 12, textAlign: 'center' }}>
            默认账号: admin / op1 密码: admin123
          </div>
        </Form>
      </Card>
    </div>
  );
}
