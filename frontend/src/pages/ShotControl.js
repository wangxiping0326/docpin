// 注射控制页 - 核心操作界面 + 自定义曲线
import React, { useState, useEffect, useRef } from 'react';
import {
  Card, Form, Select, InputNumber, Button, Row, Col,
  Progress, Descriptions, Tag, message, Space, Divider, Spin,
  Table, Popconfirm, Slider, Input,
} from 'antd';
import {
  PlayCircleOutlined, PauseCircleOutlined, StopOutlined,
  ThunderboltOutlined, PlusOutlined, DeleteOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import api from '../api';
import { addWSListener } from '../ws';

const modeOpts = [
  { label: '持续输注', value: 'cont' },
  { label: '间歇输注', value: 'jianxie' },
  { label: '按需推注', value: 'tui' },
  { label: '自定义曲线', value: 'custom' },
];

export default function ShotControl({ me }) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [st, setSt] = useState(null);
  const [progress, setProgress] = useState(0);
  const [yaoRec, setYaoRec] = useState({ recommend: 10, avg_su_lv: 5, mode_hint: 'cont' });
  const [selMode, setSelMode] = useState('cont');
  // 自定义曲线用的
  const [curvePts, setCurvePts] = useState([
    { key: 1, t: 0, rate: 5 },
    { key: 2, t: 30, rate: 8 },
    { key: 3, t: 60, rate: 3 },
  ]);
  const nextKey = useRef(4);

  const running = st?.running || false;

  const refreshState = async () => {
    try {
      const s = await api.shotStatus();
      setSt(s);
      if (s.total > 0) {
        const pct = ((s.total - s.remaining) / s.total) * 100;
        setProgress(Math.min(100, Math.max(0, pct)));
      }
    } catch (e) { /* */ }
  };

  useEffect(() => {
    refreshState();
    api.recommend().then(r => { if (r) setYaoRec(r); }).catch(() => {});
    const rm = addWSListener((data) => {
      if (data.type === 'progress') {
        setSt(data.data);
        if (data.data.total > 0) {
          const pct = ((data.data.total - data.data.remaining) / data.data.total) * 100;
          setProgress(Math.min(100, Math.max(0, pct)));
        }
      }
      if (data.type === 'shot_done' || data.type === 'shot_stopped') {
        refreshState(); setProgress(0);
      }
      if (data.type === 'alarm') {
        message.error(data.data?.msg || '报警！');
      }
    });
    const t = setInterval(refreshState, 3000);
    return () => { rm(); clearInterval(t); };
  }, []);

  const doStart = async () => {
    const vals = await form.validateFields().catch(() => null);
    if (!vals) return;
    const payload = { ...vals };
    if (selMode === 'custom') {
      payload.curve_points = curvePts;
    }
    setLoading(true);
    try {
      await api.startShot(payload);
      message.success('注射启动成功');
      refreshState();
    } catch (e) {
      message.error(e.message || '启动失败');
    } finally {
      setLoading(false);
    }
  };

  const doStop = async () => {
    setLoading(true);
    try {
      await api.stopShot();
      message.success('已发送停止指令');
      refreshState();
    } catch (e) {
      message.error(e.message || '停止失败');
    } finally {
      setLoading(false);
    }
  };

  const onModeChange = (mode) => {
    setSelMode(mode);
    if (mode === 'jianxie') form.setFieldsValue({ jian_ge: 30 });
    else if (mode === 'tui') form.setFieldsValue({ total_time: 10 });
    else if (mode === 'custom') form.setFieldsValue({ total_time: 60 });
  };

  const addCurvePt = () => {
    const last = curvePts[curvePts.length - 1];
    setCurvePts([...curvePts, { key: nextKey.current, t: (last?.t || 0) + 30, rate: last?.rate || 5 }]);
    nextKey.current++;
  };

  const updateCurvePt = (key, field, val) => {
    setCurvePts(prev => prev.map(p => p.key === key ? { ...p, [field]: val } : p));
  };

  const delCurvePt = (key) => {
    if (curvePts.length <= 2) return message.warning('至少保留2个点');
    setCurvePts(prev => prev.filter(p => p.key !== key));
  };

  const curveCols = [
    { title: '时间点(s)', dataIndex: 't', width: 110,
      render: (v, r) => <InputNumber min={0} max={86400} value={v} size="small"
        onChange={val => updateCurvePt(r.key, 't', val)} style={{ width: 90 }} /> },
    { title: '速率(mL/h)', dataIndex: 'rate', width: 110,
      render: (v, r) => <InputNumber min={0.1} max={999} step={0.1} value={v} size="small"
        onChange={val => updateCurvePt(r.key, 'rate', val)} style={{ width: 90 }} /> },
    { title: '', width: 40,
      render: (_, r) => (
        <Popconfirm title="删?" onConfirm={() => delCurvePt(r.key)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ) },
  ];

  const chartData = curvePts.map(p => ({ time: p.t, rate: p.rate })).sort((a, b) => a.time - b.time);

  return (
    <div>
      <h3 style={{ marginBottom: 14 }}>💉 注射控制台</h3>
      <Row gutter={[14, 14]}>
        <Col xs={24} lg={14}>
          <Card title="参数设置">
            <Form form={form} layout="vertical"
              initialValues={{ mode: 'cont', su_lv: 5, ji_liang: 10, total_time: 60, jian_ge: 0, notes: '' }}>
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item label="注射模式" name="mode">
                    <Select options={modeOpts} onChange={onModeChange} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="速率 (mL/h)" name="su_lv">
                    <InputNumber min={0.1} max={999} step={0.1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="剂量 (mL)" name="ji_liang"
                    extra={<span style={{ fontSize: 11, color: '#1677ff' }}>推荐: {yaoRec.recommend} mL</span>}>
                    <InputNumber min={0.1} max={999} step={0.1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item label="时长 (秒)" name="total_time">
                    <InputNumber min={1} max={86400} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="间歇间隔 (秒)" name="jian_ge">
                    <InputNumber min={0} max={3600} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="备注" name="notes">
                    <Input placeholder="可选" />
                  </Form.Item>
                </Col>
              </Row>

              {/* 自定义曲线配置 */}
              {selMode === 'custom' && (
                <Card title={<span><LineChartOutlined /> 给药曲线</span>} size="small"
                  style={{ marginBottom: 12, background: '#fafafa' }}
                  extra={<Button size="small" icon={<PlusOutlined />} onClick={addCurvePt}>加点</Button>}>
                  <Row gutter={12}>
                    <Col xs={24} md={12}>
                      <Table columns={curveCols} dataSource={curvePts} rowKey="key"
                        size="small" pagination={false} showHeader={true} />
                    </Col>
                    <Col xs={24} md={12}>
                      <ResponsiveContainer width="100%" height={180}>
                        <LineChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="time" label={{ value: '时间(s)', position: 'bottom', fontSize: 11 }} />
                          <YAxis label={{ value: '速率', angle: -90, position: 'insideLeft', fontSize: 11 }} />
                          <Tooltip />
                          <Line type="monotone" dataKey="rate" stroke="#1677ff" strokeWidth={2} dot={{ r: 3 }} />
                        </LineChart>
                      </ResponsiveContainer>
                    </Col>
                  </Row>
                </Card>
              )}

              <Space>
                <Button type="primary" icon={<PlayCircleOutlined />}
                  onClick={doStart} loading={loading} disabled={running}
                  size="large">
                  启动注射
                </Button>
                <Button danger icon={<StopOutlined />}
                  onClick={doStop} loading={loading} disabled={!running}
                  size="large">
                  停止注射
                </Button>
                {running && me?.role === 'admin' && (
                  <Button danger type="dashed" onClick={doStop}>
                    管理员强制停止
                  </Button>
                )}
              </Space>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="实时状态">
            {running ? (
              <div>
                <div style={{ textAlign: 'center', marginBottom: 12 }}>
                  <Tag color="processing" icon={<ThunderboltOutlined />}
                    style={{ fontSize: 15, padding: '4px 14px' }}>
                    注射进行中
                  </Tag>
                  {st?.started_by && (
                    <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                      操作者: {st.started_by}
                    </div>
                  )}
                </div>
                <Progress percent={Math.round(progress)}
                  status={st?.jiting ? 'exception' : (progress >= 100 ? 'success' : 'active')}
                  strokeColor={st?.jiting ? '#ff4d4f' : undefined}
                />
                <Descriptions column={1} size="small" style={{ marginTop: 12 }} bordered>
                  <Descriptions.Item label="模式">
                    <Tag color="blue">{selMode === 'cont' ? '持续输注' : selMode === 'jianxie' ? '间歇输注' : selMode === 'tui' ? '按需推注' : '自定义'}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="速率">{st?.su_lv} mL/h</Descriptions.Item>
                  <Descriptions.Item label="已用时">{st?.elapsed?.toFixed(0)} s</Descriptions.Item>
                  <Descriptions.Item label="剩余时间">{st?.remaining?.toFixed(0)} s</Descriptions.Item>
                  <Descriptions.Item label="当前压力">
                    <span style={{ color: (st?.yali_now || 0) > 80 ? '#ff4d4f' : '#52c41a', fontWeight: 'bold' }}>
                      {st?.yali_now?.toFixed(1)} kPa
                    </span>
                  </Descriptions.Item>
                  <Descriptions.Item label="剩余药量">
                    <span style={{ fontWeight: 'bold' }}>{st?.yao_left?.toFixed(2)} mL</span>
                  </Descriptions.Item>
                </Descriptions>
                {st?.jiting && (
                  <div style={{
                    background: '#ff4d4f', color: '#fff', padding: '10px 16px',
                    borderRadius: 6, marginTop: 10, textAlign: 'center',
                    fontWeight: 'bold', animation: 'blink 0.6s infinite alternate'
                  }}>
                    🛑 已紧急停注！压力或药量超限
                  </div>
                )}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#999' }}>
                <PauseCircleOutlined style={{ fontSize: 56 }} />
                <div style={{ marginTop: 10, fontSize: 15 }}>当前无注射任务</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>
                  选择模式并设置参数后启动
                </div>
                {/* 剂量推荐 */}
                <Card size="small" style={{ marginTop: 16, textAlign: 'left', background: '#f6ffed' }}>
                  <div style={{ fontSize: 13, fontWeight: 'bold' }}>💡 智能推荐</div>
                  <div>推荐剂量: {yaoRec.recommend} mL</div>
                  <div>建议速率: {yaoRec.avg_su_lv} mL/h</div>
                  <div>常用模式: {yaoRec.mode_hint}</div>
                </Card>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
