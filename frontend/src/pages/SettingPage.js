// 系统设置页 - 阈值修改 + 操作日志 + 数据清理
import React, { useState, useEffect } from 'react';
import { Card, Form, InputNumber, Button, Table, Row, Col, message, Divider, Popconfirm, Input, Statistic, Select } from 'antd';
import { SaveOutlined, HistoryOutlined, DeleteOutlined, WarningOutlined, ReloadOutlined } from '@ant-design/icons';
import api from '../api';

export default function SettingPage({ me }) {
  const [th, setTh] = useState({});
  const [logs, setLogs] = useState([]);
  const [logTotal, setLogTotal] = useState(0);
  const [logPage, setLogPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [logUser, setLogUser] = useState('');
  const [cleanDays, setCleanDays] = useState(90);
  const [todayAlarms, setTodayAlarms] = useState(null);
  const isAdmin = me?.role === 'admin';

  const loadTh = async () => {
    try {
      const [d, ta] = await Promise.all([
        api.getThresholds(),
        api.get('/api/alarm/today_count'),
      ]);
      setTh(d);
      setTodayAlarms(ta);
    } catch (e) { /* */ }
  };

  const loadLogs = async () => {
    try {
      const params = { page: logPage };
      if (logUser) params.username = logUser;
      const res = await api.opLogs(params);
      setLogs(res.list || []);
      setLogTotal(res.total || 0);
    } catch (e) { /* */ }
  };

  useEffect(() => { loadTh(); loadLogs(); }, [logPage, logUser]);

  const saveTh = async () => {
    setLoading(true);
    try {
      await api.setThresholds(th);
      message.success('阈值已更新');
    } catch (e) {
      message.error(e.message || '保存失败');
    }
    setLoading(false);
  };

  const doCleanLogs = async () => {
    try {
      await api.cleanLogs({ days: cleanDays });
      message.success(`已清理 ${cleanDays} 天前的日志`);
      loadLogs();
    } catch (e) {
      message.error(e.message || '清理失败');
    }
  };

  const logCols = [
    { title: '时间', dataIndex: 'created_at', width: 170 },
    { title: '用户', dataIndex: 'username', width: 90 },
    { title: '操作', dataIndex: 'action' },
    { title: 'IP', dataIndex: 'ip_addr', width: 130 },
  ];

  const levelNames = { warn1: '预警', warn2: '警告', jiting: '紧急停注' };

  return (
    <div>
      <h3 style={{ marginBottom: 14 }}>⚙️ 系统设置</h3>
      <Row gutter={[14, 14]}>
        <Col xs={24} md={12}>
          <Card title="报警阈值设置">
            {isAdmin ? (
              <div>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 4, fontWeight: 'bold' }}>
                    压力预警值 (kPa)
                    <span style={{ fontSize: 11, color: '#999', marginLeft: 8 }}>一级报警</span>
                  </div>
                  <InputNumber min={0} max={200} value={th.thresh_yali_warn}
                    onChange={v => setTh(prev => ({ ...prev, thresh_yali_warn: v }))}
                    style={{ width: '100%' }} />
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                    压力超过此值触发黄色预警通知
                  </div>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 4, fontWeight: 'bold' }}>
                    压力警告值 (kPa)
                    <span style={{ fontSize: 11, color: '#faad14', marginLeft: 8 }}>二级报警</span>
                  </div>
                  <InputNumber min={0} max={200} value={th.thresh_yaol_warn}
                    onChange={v => setTh(prev => ({ ...prev, thresh_yaol_warn: v }))}
                    style={{ width: '100%' }} />
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                    压力超过此值触发橙色警告通知
                  </div>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 4, fontWeight: 'bold' }}>
                    紧急停注值 (kPa)
                    <span style={{ fontSize: 11, color: '#ff4d4f', marginLeft: 8 }}>三级 - 自动停注</span>
                  </div>
                  <InputNumber min={0} max={200} value={th.thresh_jiting}
                    onChange={v => setTh(prev => ({ ...prev, thresh_jiting: v }))}
                    style={{ width: '100%' }} />
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                    压力达到此值立即下发紧急中断指令
                  </div>
                </div>
                <Button type="primary" icon={<SaveOutlined />} onClick={saveTh} loading={loading}>
                  保存阈值设置
                </Button>
              </div>
            ) : (
              <div style={{ color: '#999', textAlign: 'center', padding: 30 }}>
                仅管理员可修改阈值设置
              </div>
            )}

            {/* 今日报警统计 */}
            {todayAlarms && (
              <Card size="small" title="今日报警统计" style={{ marginTop: 16, background: '#fafafa' }}>
                <Row gutter={8}>
                  <Col span={8}>
                    <Statistic title="总计" value={todayAlarms.total} valueStyle={{ fontSize: 20 }} />
                  </Col>
                  <Col span={8}>
                    <Statistic title="预警" value={todayAlarms.warn1} valueStyle={{ fontSize: 20, color: '#faad14' }} />
                  </Col>
                  <Col span={8}>
                    <Statistic title="警告/停注" value={todayAlarms.warn2 + todayAlarms.jiting}
                      valueStyle={{ fontSize: 20, color: '#ff4d4f' }} />
                  </Col>
                </Row>
              </Card>
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title={<span><HistoryOutlined /> 操作日志</span>} extra={
            <div style={{ display: 'flex', gap: 8 }}>
              <Input.Search placeholder="搜用户名" size="small"
                onSearch={v => { setLogUser(v); setLogPage(1); }} style={{ width: 130 }} />
              <Button size="small" icon={<ReloadOutlined />} onClick={loadLogs} />
            </div>
          }>
            <Table columns={logCols} dataSource={logs} rowKey="id" size="small"
              pagination={{ current: logPage, total: logTotal, pageSize: 20, onChange: setLogPage }}
            />
          </Card>

          {isAdmin && (
            <Card title="数据维护" size="small" style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>清理</span>
                <Select value={cleanDays} onChange={setCleanDays} style={{ width: 100 }}
                  options={[
                    { label: '30天前', value: 30 },
                    { label: '60天前', value: 60 },
                    { label: '90天前', value: 90 },
                    { label: '180天前', value: 180 },
                  ]} />
                <span>的操作日志</span>
                <Popconfirm title="确认清理？不可恢复！" onConfirm={doCleanLogs}
                  icon={<WarningOutlined style={{ color: '#ff4d4f' }} />}>
                  <Button danger size="small" icon={<DeleteOutlined />}>执行清理</Button>
                </Popconfirm>
              </div>
            </Card>
          )}
        </Col>
      </Row>
    </div>
  );
}
