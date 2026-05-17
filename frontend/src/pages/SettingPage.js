// 系统设置页 - 阈值修改 + 操作日志(只读归档) + 修改密码
import React, { useState, useEffect } from 'react';
import { Card, Form, InputNumber, Button, Table, Row, Col, message, Divider, Popconfirm, Input, Statistic, Select, Modal } from 'antd';
import { SaveOutlined, HistoryOutlined, ReloadOutlined, LockOutlined, DownloadOutlined } from '@ant-design/icons';
import api from '../api';

export default function SettingPage({ me }) {
  const [th, setTh] = useState({});
  const [logs, setLogs] = useState([]);
  const [logTotal, setLogTotal] = useState(0);
  const [logPage, setLogPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [logUser, setLogUser] = useState('');
  const [todayAlarms, setTodayAlarms] = useState(null);
  const [pwdOpen, setPwdOpen] = useState(false);
  const [esigOpen, setEsigOpen] = useState(false);
  const [esigAction, setEsigAction] = useState('');
  const [esigPwd, setEsigPwd] = useState('');
  const [esigCallback, setEsigCallback] = useState(null);
  const [archiveDays, setArchiveDays] = useState(90);
  const [oldPwd, setOldPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [pwdLoading, setPwdLoading] = useState(false);
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

  // 电子签名弹窗
  const requireEsig = (action, callback) => {
    setEsigAction(action);
    setEsigPwd('');
    setEsigCallback(() => callback);
    setEsigOpen(true);
  };

  const doEsig = async () => {
    try {
      await api.get('/api/auth/esig');
      // 实际上应该 POST esig 验证
      const res = await fetch('/api/auth/esig', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + localStorage.getItem('docpin_tok'),
        },
        body: JSON.stringify({ action: esigAction, password: esigPwd }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || '验证失败');
      message.success('电子签名验证成功');
      setEsigOpen(false);
      if (esigCallback) esigCallback();
    } catch (e) {
      message.error(e.message || '电子签名失败');
    }
  };

  const saveTh = () => {
    requireEsig('修改报警阈值', async () => {
      setLoading(true);
      try {
        await api.setThresholds(th);
        message.success('阈值已更新');
      } catch (e) {
        message.error(e.message || '保存失败');
      }
      setLoading(false);
    });
  };

  const doArchive = async () => {
    try {
      const blob = await fetch('/api/stats/logs/archive', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + localStorage.getItem('docpin_tok'),
        },
        body: JSON.stringify({ days: archiveDays }),
      }).then(r => {
        if (!r.ok) throw new Error('归档失败');
        return r.blob();
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'audit_log_archive_' + new Date().toISOString().slice(0, 10) + '.csv';
      a.click();
      window.URL.revokeObjectURL(url);
      message.success('审计日志已归档导出（原记录保留）');
      loadLogs();
    } catch (e) {
      message.error(e.message || '归档失败');
    }
  };

  const doChangePwd = async () => {
    if (!oldPwd || !newPwd) return message.warning('填完整');
    setPwdLoading(true);
    try {
      const res = await fetch('/api/auth/change-pwd', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + localStorage.getItem('docpin_tok'),
        },
        body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || '修改失败');
      message.success('密码已更新，请重新登录');
      setPwdOpen(false);
      setOldPwd(''); setNewPwd('');
    } catch (e) {
      message.error(e.message || '修改失败');
    }
    setPwdLoading(false);
  };

  const logCols = [
    { title: '时间', dataIndex: 'created_at', width: 170 },
    { title: '用户', dataIndex: 'username', width: 90 },
    { title: '操作', dataIndex: 'action' },
    { title: 'IP', dataIndex: 'ip_addr', width: 130 },
    { title: '签名', dataIndex: 'signature', width: 80, render: v => v ? <span style={{ color: '#52c41a', fontSize: 11 }}>已签名</span> : '-' },
  ];

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
                    压力预警值 (kPa) <span style={{ fontSize: 11, color: '#999' }}>一级</span>
                  </div>
                  <InputNumber min={0} max={200} value={th.thresh_yali_warn}
                    onChange={v => setTh(prev => ({ ...prev, thresh_yali_warn: v }))}
                    style={{ width: '100%' }} />
                </div>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 4, fontWeight: 'bold' }}>
                    压力警告值 (kPa) <span style={{ fontSize: 11, color: '#faad14' }}>二级</span>
                  </div>
                  <InputNumber min={0} max={200} value={th.thresh_yaol_warn}
                    onChange={v => setTh(prev => ({ ...prev, thresh_yaol_warn: v }))}
                    style={{ width: '100%' }} />
                </div>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 4, fontWeight: 'bold' }}>
                    紧急停注值 (kPa) <span style={{ fontSize: 11, color: '#ff4d4f' }}>三级</span>
                  </div>
                  <InputNumber min={0} max={200} value={th.thresh_jiting}
                    onChange={v => setTh(prev => ({ ...prev, thresh_jiting: v }))}
                    style={{ width: '100%' }} />
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>达到此值自动触发紧急停注</div>
                </div>
                <Button type="primary" icon={<SaveOutlined />} onClick={saveTh} loading={loading}>
                  保存阈值（需电子签名）
                </Button>
                <Divider />
                <Button icon={<LockOutlined />} onClick={() => setPwdOpen(true)}>
                  修改密码
                </Button>
              </div>
            ) : (
              <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>
                仅管理员可修改 <br />
                <Button size="small" style={{ marginTop: 8 }} icon={<LockOutlined />}
                  onClick={() => setPwdOpen(true)}>修改密码</Button>
              </div>
            )}
            {todayAlarms && (
              <Card size="small" title="今日报警" style={{ marginTop: 16, background: '#fafafa' }}>
                <Row gutter={8}>
                  <Col span={8}><Statistic title="总计" value={todayAlarms.total} valueStyle={{ fontSize: 20 }} /></Col>
                  <Col span={8}><Statistic title="预警" value={todayAlarms.warn1} valueStyle={{ fontSize: 20, color: '#faad14' }} /></Col>
                  <Col span={8}><Statistic title="警告/停注" value={todayAlarms.warn2 + todayAlarms.jiting} valueStyle={{ fontSize: 20, color: '#ff4d4f' }} /></Col>
                </Row>
              </Card>
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title={<span><HistoryOutlined /> 审计日志（防篡改）</span>} extra={
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
            <Card title="日志归档导出" size="small" style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>导出</span>
                <Select value={archiveDays} onChange={setArchiveDays} style={{ width: 100 }}
                  options={[
                    { label: '30天前', value: 30 },
                    { label: '60天前', value: 60 },
                    { label: '90天前', value: 90 },
                    { label: '180天前', value: 180 },
                  ]} />
                <span>的操作日志</span>
                <Button size="small" icon={<DownloadOutlined />} onClick={doArchive}>
                  归档导出（不删除原记录）
                </Button>
              </div>
            </Card>
          )}
        </Col>
      </Row>

      {/* 电子签名弹窗 */}
      <Modal title="电子签名验证" open={esigOpen} onOk={doEsig} onCancel={() => setEsigOpen(false)}>
        <div style={{ marginBottom: 8 }}>操作: <strong>{esigAction}</strong></div>
        <div style={{ marginBottom: 4 }}>请输入密码确认:</div>
        <Input.Password value={esigPwd} onChange={e => setEsigPwd(e.target.value)}
          placeholder="输入当前密码" />
      </Modal>

      {/* 修改密码弹窗 */}
      <Modal title="修改密码" open={pwdOpen} onOk={doChangePwd} onCancel={() => { setPwdOpen(false); setOldPwd(''); setNewPwd(''); }}
        confirmLoading={pwdLoading}>
        <div style={{ marginBottom: 8 }}>旧密码</div>
        <Input.Password value={oldPwd} onChange={e => setOldPwd(e.target.value)} />
        <div style={{ marginBottom: 8, marginTop: 12 }}>新密码（≥8位，大小写/数字/符号至少三类）</div>
        <Input.Password value={newPwd} onChange={e => setNewPwd(e.target.value)} />
      </Modal>
    </div>
  );
}
