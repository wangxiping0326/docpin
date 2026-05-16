// 用户管理 - 管理员专用
import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Modal, Input, Select, Popconfirm, message, Space, Tag } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import api from '../api';

export default function UserPage({ me }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [newRole, setNewRole] = useState('operator');

  const load = async () => {
    setLoading(true);
    try {
      const d = await api.listUsers();
      setUsers(d || []);
    } catch (e) { /* */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const doAdd = async () => {
    if (!newName.trim() || !newPwd.trim()) return message.warning('填完整');
    try {
      await api.addUser({ username: newName.trim(), password: newPwd, role: newRole });
      message.success('用户创建成功');
      setAddOpen(false);
      setNewName('');
      setNewPwd('');
      load();
    } catch (e) { message.error(e.message || '创建失败'); }
  };

  const doDel = async (id) => {
    try {
      await api.delUser(id);
      message.success('已删除');
      load();
    } catch (e) { message.error(e.message || '删除失败'); }
  };

  const cols = [
    { title: 'ID', dataIndex: 'id', width: 50 },
    { title: '用户名', dataIndex: 'username' },
    {
      title: '角色', dataIndex: 'role', width: 90,
      render: v => v === 'admin' ? <Tag color="red">管理员</Tag> : <Tag color="blue">操作员</Tag>
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170 },
    {
      title: '操作', width: 80,
      render: (_, r) => (
        r.role !== 'admin' ? (
          <Popconfirm title="确认删除?" onConfirm={() => doDel(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        ) : null
      )
    },
  ];

  if (me?.role !== 'admin') {
    return <Card><div style={{ textAlign: 'center', color: '#999', padding: 40 }}>仅管理员可访问</div></Card>;
  }

  return (
    <div>
      <h3 style={{ marginBottom: 14 }}>👥 用户管理</h3>
      <Card title="用户列表" extra={
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
          添加用户
        </Button>
      }>
        <Table columns={cols} dataSource={users} rowKey="id" loading={loading}
          size="small" pagination={false}
        />
      </Card>

      <Modal title="添加用户" open={addOpen} onOk={doAdd} onCancel={() => setAddOpen(false)}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>用户名</div>
          <Input value={newName} onChange={e => setNewName(e.target.value)} />
          <div>密码</div>
          <Input.Password value={newPwd} onChange={e => setNewPwd(e.target.value)} />
          <div>角色</div>
          <Select value={newRole} onChange={setNewRole} style={{ width: '100%' }}
            options={[
              { label: '操作员', value: 'operator' },
              { label: '管理员', value: 'admin' },
            ]}
          />
        </Space>
      </Modal>
    </div>
  );
}
