// 设备管理页
import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Tag, Modal, Input, Row, Col, Space,
  Descriptions, message, Popconfirm, Tooltip, Badge, Empty,
} from 'antd';
import {
  PlusOutlined, LinkOutlined, DisconnectOutlined, UsbOutlined,
  DeleteOutlined, ReloadOutlined, CheckCircleOutlined,
  CloseCircleOutlined, MinusCircleOutlined, ApiOutlined,
} from '@ant-design/icons';
import api from '../api';

export default function DevicePage() {
  const [devSt, setDevSt] = useState(null);
  const [loading, setLoading] = useState(false);
  const [regOpen, setRegOpen] = useState(false);
  const [regUid, setRegUid] = useState('');
  const [regName, setRegName] = useState('');
  const [ports, setPorts] = useState([]);
  const [healthWarns, setHealthWarns] = useState([]);
  const [detailDev, setDetailDev] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [d, p, h] = await Promise.all([
        api.devStatus(),
        api.devPorts(),
        api.get('/api/device/health'),
      ]);
      setDevSt(d);
      setPorts(p?.ports || []);
      setHealthWarns(h?.warnings || []);
    } catch (e) { /* */ }
    setLoading(false);
  };

  useEffect(() => { loadAll(); }, []);

  const doRegister = async () => {
    if (!regUid.trim()) return message.warning('填设备ID');
    try {
      await api.regDevice({ uid: regUid.trim(), name: regName.trim() });
      message.success('注册成功');
      setRegOpen(false);
      setRegUid('');
      setRegName('');
      loadAll();
    } catch (e) { message.error(e.message || '注册失败'); }
  };

  const doConnect = async (uid) => {
    try {
      await api.connectDev(uid);
      message.success('已连接 ' + uid);
      loadAll();
    } catch (e) { message.error(e.message || '连接失败'); }
  };

  const doDisconn = async (uid) => {
    try {
      await api.disconnDev(uid);
      message.success('已断开 ' + uid);
      loadAll();
    } catch (e) { message.error(e.message || '断开失败'); }
  };

  const doDelete = async (uid) => {
    try {
      await api.delDevice(uid);
      message.success('已删除设备');
      loadAll();
    } catch (e) {
      message.error('删除失败: ' + (e.message || e));
    }
  };

  const showDetail = async (uid) => {
    try {
      const d = await api.get('/api/device/detail/' + uid);
      setDetailDev(d);
      setDetailOpen(true);
    } catch (e) { message.error('查不到设备详情'); }
  };

  const statusTag = (s) => {
    if (s === 'online') return <Tag color="green" icon={<CheckCircleOutlined />}>在线</Tag>;
    if (s === 'working') return <Tag color="processing" icon={<ApiOutlined />}>工作中</Tag>;
    return <Tag color="default" icon={<MinusCircleOutlined />}>离线</Tag>;
  };

  const cols = [
    { title: '设备ID', dataIndex: 'device_uid', render: (v) => <a onClick={() => showDetail(v)}>{v}</a> },
    { title: '名称', dataIndex: 'dev_name' },
    { title: '状态', dataIndex: 'status', render: statusTag },
    { title: '最后在线', dataIndex: 'last_seen', width: 170, render: v => v || '-' },
    { title: '注册时间', dataIndex: 'registered_at', width: 170 },
    {
      title: '操作', width: 220,
      render: (_, r) => (
        <Space>
          <Tooltip title="连接">
            <Button size="small" type="link" icon={<LinkOutlined />}
              onClick={() => doConnect(r.device_uid)}
              disabled={r.status === 'online' || r.status === 'working'}>
            </Button>
          </Tooltip>
          <Tooltip title="断开">
            <Button size="small" type="link" danger icon={<DisconnectOutlined />}
              onClick={() => doDisconn(r.device_uid)}
              disabled={r.status === 'offline'}>
            </Button>
          </Tooltip>
          <Tooltip title="删除">
            <Popconfirm title="确认删除此设备？" onConfirm={() => doDelete(r.device_uid)}>
              <Button size="small" type="link" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Tooltip>
        </Space>
      )
    },
  ];

  return (
    <div>
      <h3 style={{ marginBottom: 14 }}>🔌 设备管理</h3>
      <Row gutter={[14, 14]}>
        <Col xs={24} md={8}>
          <Card title="系统状态" extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadAll}>刷新</Button>}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="运行模式">
                <Tag color={devSt?.sim_mode ? 'orange' : 'green'}>
                  {devSt?.sim_mode ? '模拟模式' : '真实硬件'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="串口">
                {devSt?.com_port || (devSt?.sim_mode ? '(模拟)' : '未检测到')}
              </Descriptions.Item>
              <Descriptions.Item label="已注册设备">{devSt?.devices?.length || 0} 台</Descriptions.Item>
              <Descriptions.Item label="在线设备">{devSt?.online_count || 0} 台</Descriptions.Item>
              <Descriptions.Item label="最后数据">
                {devSt?.last_data_time || '暂无'}
              </Descriptions.Item>
              <Descriptions.Item label="串口错误">{devSt?.serial_errors || 0} 次</Descriptions.Item>
            </Descriptions>
          </Card>

          {/* 可用串口列表 */}
          <Card title="可用串口" size="small" style={{ marginTop: 14 }}>
            {ports.length > 0 ? (
              <Table dataSource={ports} rowKey="device" size="small" pagination={false}
                columns={[
                  { title: '端口', dataIndex: 'device', render: v => <code>{v}</code> },
                  { title: '名称', dataIndex: 'name' },
                ]}
              />
            ) : (
              <Empty description="未检测到串口设备" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>

          {/* 健康警告 */}
          {healthWarns.length > 0 && (
            <Card title="⚠️ 健康警告" size="small" style={{ marginTop: 14, background: '#fff2f0' }}>
              {healthWarns.map((w, i) => <div key={i} style={{ color: '#ff4d4f', fontSize: 12 }}>{w}</div>)}
            </Card>
          )}
        </Col>

        <Col xs={24} md={16}>
          <Card title="已注册设备" extra={
            <Space>
              <Button type="primary" size="small" icon={<PlusOutlined />}
                onClick={() => setRegOpen(true)}>
                注册设备
              </Button>
              <Button size="small" icon={<ReloadOutlined />} onClick={loadAll} />
            </Space>
          }>
            <Table columns={cols} dataSource={devSt?.devices || []} rowKey="device_uid"
              loading={loading} size="small"
              pagination={false}
              locale={{ emptyText: '暂无注册设备，请点击"注册设备"添加' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 注册弹窗 */}
      <Modal title="注册新设备" open={regOpen} onOk={doRegister} onCancel={() => setRegOpen(false)}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <div><strong>设备唯一ID</strong></div>
          <Input placeholder="如: INJ-001" value={regUid}
            onChange={e => setRegUid(e.target.value)}
            prefix={<UsbOutlined />} />
          <div style={{ fontSize: 11, color: '#999' }}>注射器上的唯一序列号</div>
          <div style={{ marginTop: 8 }}><strong>设备名称（可选）</strong></div>
          <Input placeholder="如: 1号手术室注射器" value={regName}
            onChange={e => setRegName(e.target.value)} />
        </Space>
      </Modal>

      {/* 设备详情弹窗 */}
      <Modal title="设备详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null}>
        {detailDev && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="设备ID">{detailDev.device_uid}</Descriptions.Item>
            <Descriptions.Item label="名称">{detailDev.dev_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态">{statusTag(detailDev.status)}</Descriptions.Item>
            <Descriptions.Item label="最后在线">{detailDev.last_seen || '-'}</Descriptions.Item>
            <Descriptions.Item label="注册时间" span={2}>{detailDev.registered_at}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
}
