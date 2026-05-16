// 报警监控页 - 列表 + 统计
import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Select, Row, Col } from 'antd';
import { PieChart, Pie, Cell, Tooltip, Legend } from 'recharts';
import { addWSListener } from '../ws';
import api from '../api';
import dayjs from 'dayjs';

const COLORS = ['#faad14', '#ff7a45', '#ff4d4f'];

const levelTag = (lv) => {
  if (lv === 'warn1') return <Tag color="gold">预警</Tag>;
  if (lv === 'warn2') return <Tag color="orange">警告</Tag>;
  return <Tag color="red">紧急停注</Tag>;
};

export default function AlarmPage() {
  const [list, setList] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [level, setLevel] = useState('');
  const [loading, setLoading] = useState(false);
  const [pieData, setPieData] = useState([]);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.alarms({ page, page_size: 20, level });
      setList(res.list || []);
      setTotal(res.total || 0);
    } catch (e) { /* */ }
    setLoading(false);
  };

  const loadPie = async () => {
    try {
      const d = await api.alarmStats();
      setPieData(d || []);
    } catch (e) { /* */ }
  };

  useEffect(() => {
    load(); loadPie();
    const rm = addWSListener((data) => {
      if (data.type === 'alarm') {
        load(); loadPie(); // 有新报警就刷新
      }
    });
    return () => rm();
  }, [page, level]);

  const cols = [
    { title: '时间', dataIndex: 'created_at', width: 170 },
    { title: '级别', dataIndex: 'alarm_level', width: 100, render: levelTag },
    { title: '报警信息', dataIndex: 'msg' },
    { title: '压力值', dataIndex: 'yali_val', width: 90, render: v => v?.toFixed(1) + ' kPa' },
    { title: '药量值', dataIndex: 'yao_val', width: 90, render: v => v?.toFixed(2) + ' mL' },
  ];

  return (
    <div>
      <h3 style={{ marginBottom: 14 }}>🚨 报警监控</h3>
      <Row gutter={[14, 14]}>
        <Col xs={24} md={14}>
          <Card title="报警列表" extra={
            <Select placeholder="级别筛选" allowClear style={{ width: 120 }} value={level || undefined}
              onChange={v => { setLevel(v || ''); setPage(1); }}
              options={[
                { label: '预警', value: 'warn1' },
                { label: '警告', value: 'warn2' },
                { label: '紧急停注', value: 'jiting' },
              ]}
            />
          }>
            <Table columns={cols} dataSource={list} rowKey="id" loading={loading} size="small"
              pagination={{ current: page, total, pageSize: 20, onChange: setPage }}
            />
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card title="报警统计">
            {pieData.length > 0 ? (
              <PieChart width={300} height={280}>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label>
                  {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            ) : (
              <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>暂无报警数据</div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
