// 仪表盘 - 概览页面，几张卡片 + 实时状态 + 趋势迷你图
import React, { useState, useEffect } from 'react';
import { Card, Statistic, Row, Col, Tag, Table, Spin, List, Progress } from 'antd';
import {
  ExperimentOutlined, AlertOutlined, CheckCircleOutlined,
  ThunderboltOutlined, LineChartOutlined, ClockCircleOutlined,
  FireOutlined, DashboardOutlined,
} from '@ant-design/icons';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import api from '../api';
import { addWSListener } from '../ws';

export default function Dash() {
  const [shotSt, setShotSt] = useState(null);
  const [overview, setOverview] = useState(null);
  const [alarmList, setAlarmList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [weekData, setWeekData] = useState([]);
  const [progress, setProgress] = useState(0);

  const refresh = async () => {
    try {
      const [st, ov, dStats] = await Promise.all([
        api.shotStatus(),
        api.get('/api/stats/overview'),
        api.doseStats({ period: 'day' }),
      ]);
      setShotSt(st);
      setOverview(ov);
      setWeekData(ov?.week_trend || []);
      setAlarmList(ov?.latest_alarms || []);
    } catch (e) { /* */ }
    setLoading(false);
  };

  useEffect(() => {
    refresh();
    const rm = addWSListener((data) => {
      if (data.type === 'progress') {
        setShotSt(data.data);
        if (data.data.total > 0) {
          setProgress(Math.min(100, ((data.data.total - data.data.remaining) / data.data.total) * 100));
        }
      }
      if (data.type === 'shot_done' || data.type === 'shot_stopped') {
        setShotSt(prev => prev ? { ...prev, running: false } : null);
        setProgress(0);
        setTimeout(() => refresh(), 500);
      }
      if (data.type === 'alarm') {
        refresh();
      }
    });
    const t = setInterval(refresh, 10000);
    return () => { rm(); clearInterval(t); };
  }, []);

  const running = shotSt?.running || false;
  const modeMap = { cont: '持续输注', jianxie: '间歇输注', tui: '按需推注', custom: '自定义' };
  const modeColors = { cont: '#1677ff', jianxie: '#faad14', tui: '#52c41a', custom: '#722ed1' };

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />;

  return (
    <div>
      <h3 style={{ marginBottom: 14 }}>📊 系统概览</h3>

      {/* 第一行卡片 */}
      <Row gutter={[14, 14]}>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable>
            <Statistic
              title="注射状态"
              value={running ? '运行中' : '空闲'}
              valueStyle={{ color: running ? '#52c41a' : '#999', fontSize: 22 }}
              prefix={running ? <ThunderboltOutlined spin /> : <CheckCircleOutlined />}
            />
            {running && (
              <div style={{ marginTop: 8 }}>
                <Tag color={modeColors[shotSt?.mode] || 'blue'}>
                  {modeMap[shotSt?.mode] || shotSt?.mode}
                </Tag>
                <Progress percent={Math.round(progress)} size="small" style={{ marginTop: 6 }} />
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable>
            <Statistic title="今日注射" value={overview?.today_shots || 0}
              suffix="次" prefix={<ExperimentOutlined />}
              valueStyle={{ color: '#1677ff', fontSize: 22 }}
            />
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
              总计: {overview?.total_shots || 0} 次
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable>
            <Statistic title="报警总数" value={overview?.total_alarms || 0}
              suffix="次" prefix={<AlertOutlined />}
              valueStyle={{ color: (overview?.total_alarms || 0) > 0 ? '#ff4d4f' : '#999', fontSize: 22 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable>
            <Statistic title="注册设备" value={overview?.device_count || 0}
              suffix="台" prefix={<DashboardOutlined />}
              valueStyle={{ fontSize: 22 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 第二行 - 图表 + 实时状态 */}
      <Row gutter={[14, 14]} style={{ marginTop: 14 }}>
        <Col xs={24} lg={14}>
          <Card title={<span><LineChartOutlined /> 近7天注射趋势</span>}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={weekData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="dt" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip />
                <Bar dataKey="cnt" fill="#1677ff" name="注射次数" />
                <Bar dataKey="total_dose" fill="#52c41a" name="总剂量(mL)" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title={<span><AlertOutlined /> 最近报警</span>}>
            {alarmList.length > 0 ? (
              <List size="small" dataSource={alarmList}
                renderItem={item => {
                  const lvlColor = item.alarm_level === 'jiting' ? '#ff4d4f' : item.alarm_level === 'warn2' ? '#faad14' : '#1677ff';
                  return (
                    <List.Item>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
                        <span style={{ color: lvlColor, fontWeight: 'bold', fontSize: 16 }}>
                          {item.alarm_level === 'jiting' ? '🛑' : item.alarm_level === 'warn2' ? '⚠️' : '🔔'}
                        </span>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 13 }}>{item.msg}</div>
                          <div style={{ fontSize: 11, color: '#999' }}>
                            压力:{item.yali_val?.toFixed(1)} | 药量:{item.yao_val?.toFixed(2)} | {item.created_at}
                          </div>
                        </div>
                      </div>
                    </List.Item>
                  );
                }}
              />
            ) : (
              <div style={{ textAlign: 'center', padding: 30, color: '#999' }}>暂无报警记录 👍</div>
            )}
          </Card>
        </Col>
      </Row>

      {/* 实时监测 - 只在注射时显示 */}
      {running && shotSt && (
        <Card title="实时监测数据" style={{ marginTop: 14 }}>
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={6}>
              <Card size="small" style={{ background: '#f6ffed' }}>
                <Statistic title="当前压力" value={shotSt.yali_now?.toFixed(1)} suffix="kPa"
                  valueStyle={{ color: shotSt.yali_now > 80 ? '#ff4d4f' : '#52c41a', fontSize: 24 }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card size="small" style={{ background: '#e6f4ff' }}>
                <Statistic title="剩余药量" value={shotSt.yao_left?.toFixed(2)} suffix="mL"
                  valueStyle={{ color: '#1677ff', fontSize: 24 }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card size="small" style={{ background: '#fff7e6' }}>
                <Statistic title="当前速率" value={shotSt.su_lv} suffix="mL/h"
                  valueStyle={{ fontSize: 24 }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card size="small" style={{ background: '#f9f0ff' }}>
                <Statistic title="剩余时间" value={shotSt.remaining?.toFixed(0)} suffix="s"
                  valueStyle={{ fontSize: 24 }}
                />
              </Card>
            </Col>
          </Row>
          <Progress percent={Math.round(progress)} status={shotSt?.jiting ? 'exception' : 'active'}
            style={{ marginTop: 12 }}
          />
        </Card>
      )}
    </div>
  );
}
