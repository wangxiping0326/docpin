// 用药数据管理 - 记录查询 + 统计图 + 导出 + 模式分析
import React, { useState, useEffect } from 'react';
import {
  Card, Table, Select, DatePicker, Button, Row, Col, Space,
  Statistic, Tag, Modal, Descriptions,
} from 'antd';
import {
  DownloadOutlined, BarChartOutlined, PieChartOutlined,
  InfoCircleOutlined, FilterOutlined,
} from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts';
import api from '../api';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;

const PIE_COLORS = ['#1677ff', '#52c41a', '#faad14', '#722ed1'];
const modeNames = { cont: '持续输注', jianxie: '间歇输注', tui: '按需推注', custom: '自定义曲线' };
const statusNames = { done: '完成', stopped: '手动停止', jiting: '紧急停注', running: '运行中' };
const statusColors = { done: '#52c41a', stopped: '#faad14', jiting: '#ff4d4f', running: '#1677ff' };

export default function DataPage() {
  const [list, setList] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [modeFilter, setMode] = useState('');
  const [dateRange, setDateRange] = useState(null);
  const [barData, setBarData] = useState([]);
  const [period, setPeriod] = useState('day');
  const [modeStats, setModeStats] = useState([]);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRow, setDetailRow] = useState(null);
  const [summaryDate, setSummaryDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [dailySum, setDailySum] = useState(null);

  const loadHistory = async () => {
    setLoading(true);
    const params = { page, page_size: 15 };
    if (modeFilter) params.mode = modeFilter;
    if (dateRange) {
      params.start_d = dateRange[0].format('YYYY-MM-DD');
      params.end_d = dateRange[1].format('YYYY-MM-DD');
    }
    try {
      const res = await api.shotHistory(params);
      setList(res.list || []);
      setTotal(res.total || 0);
    } catch (e) { /* */ }
    setLoading(false);
  };

  const loadCharts = async () => {
    try {
      const [d, ms, ds] = await Promise.all([
        api.doseStats({ period }),
        api.modeStats(),
        api.dailySummary({ date: summaryDate }),
      ]);
      setBarData(d || []);
      setModeStats(ms || []);
      setDailySum(ds);
    } catch (e) { /* */ }
  };

  useEffect(() => { loadHistory(); loadCharts(); }, [page, modeFilter, dateRange, period, summaryDate]);

  const doExport = async () => {
    try {
      const blob = await api.exportExcel({});
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = '注射记录_' + dayjs().format('YYYYMMDD_HHmmss') + '.csv';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { alert('导出失败: ' + (e.message || e)); }
  };

  const showDetail = (row) => {
    setDetailRow(row);
    setDetailOpen(true);
  };

  const columns = [
    { title: '#', dataIndex: 'id', width: 50 },
    { title: '操作员', dataIndex: 'username', width: 80 },
    {
      title: '模式', dataIndex: 'shot_mode', width: 80,
      render: v => <Tag>{modeNames[v] || v}</Tag>
    },
    { title: '剂量', dataIndex: 'ji_liang', width: 70, render: v => v + ' mL' },
    { title: '速率', dataIndex: 'su_lv', width: 70, render: v => v + ' mL/h' },
    { title: '时长', dataIndex: 'total_time', width: 70, render: v => v + ' s' },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: v => <span style={{ color: statusColors[v] || '#999', fontWeight: 'bold' }}>
        {statusNames[v] || v}
      </span>
    },
    { title: '开始时间', dataIndex: 'started_at', width: 160 },
    {
      title: '', width: 50,
      render: (_, r) => (
        <Button type="link" size="small" icon={<InfoCircleOutlined />}
          onClick={() => showDetail(r)} />
      ),
    },
  ];

  // 模式统计饼图的格式
  const pieData = modeStats.map(m => ({
    name: modeNames[m.shot_mode] || m.shot_mode,
    value: m.cnt,
    avgDose: m.avg_dose?.toFixed(1),
    avgTime: m.avg_time?.toFixed(0),
  }));

  return (
    <div>
      <h3 style={{ marginBottom: 14 }}>📋 用药数据管理</h3>

      {/* 统计卡片 */}
      <Row gutter={[14, 14]} style={{ marginBottom: 14 }}>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic title="今日注射" value={dailySum?.shot_count || 0} suffix="次" />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic title="今日剂量" value={dailySum?.total_dose || 0} suffix="mL" precision={1} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic title="今日报警" value={dailySum?.alarm_count || 0} suffix="次"
              valueStyle={{ color: (dailySum?.alarm_count || 0) > 0 ? '#ff4d4f' : '#52c41a' }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic title="总记录数" value={total} suffix="条" />
          </Card>
        </Col>
      </Row>

      {/* 图表行 */}
      <Row gutter={[14, 14]} style={{ marginBottom: 14 }}>
        <Col xs={24} lg={14}>
          <Card title={<span><BarChartOutlined /> 剂量趋势</span>}
            extra={
              <Select value={period} onChange={setPeriod} style={{ width: 90 }}
                options={[
                  { label: '按日', value: 'day' },
                  { label: '按周', value: 'week' },
                  { label: '按月', value: 'month' },
                ]}
              />
            }>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={barData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="dt" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip />
                <Legend />
                <Bar dataKey="total_dose" fill="#1677ff" name="总剂量(mL)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title={<span><PieChartOutlined /> 模式分布</span>}>
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                    outerRadius={80} label={({ name, value }) => `${name}: ${value}`}>
                    {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(val, name, props) => [
                    `${val} 次 (均量:${props.payload.avgDose}mL, 均时:${props.payload.avgTime}s)`, name
                  ]} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>暂无数据</div>
            )}
          </Card>
        </Col>
      </Row>

      {/* 记录表格 */}
      <Card title="注射记录" extra={
        <Space wrap>
          <RangePicker onChange={v => { setDateRange(v || null); setPage(1); }}
            format="YYYY-MM-DD" allowClear size="small" />
          <Select placeholder="模式筛选" allowClear style={{ width: 110 }} value={modeFilter || undefined}
            onChange={v => { setMode(v || ''); setPage(1); }} size="small"
            options={Object.entries(modeNames).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Button icon={<DownloadOutlined />} onClick={doExport} size="small">导出Excel</Button>
        </Space>
      }>
        <Table columns={columns} dataSource={list} rowKey="id" loading={loading} size="small"
          pagination={{
            current: page, total, pageSize: 15, onChange: setPage,
            showTotal: (t) => `共 ${t} 条`,
          }}
          scroll={{ x: 800 }}
        />
      </Card>

      {/* 详情弹窗 */}
      <Modal title="注射记录详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={500}>
        {detailRow && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="ID">{detailRow.id}</Descriptions.Item>
            <Descriptions.Item label="操作员">{detailRow.username}</Descriptions.Item>
            <Descriptions.Item label="模式">
              <Tag>{modeNames[detailRow.shot_mode] || detailRow.shot_mode}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <span style={{ color: statusColors[detailRow.status] || '#999' }}>
                {statusNames[detailRow.status] || detailRow.status}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label="剂量">{detailRow.ji_liang} mL</Descriptions.Item>
            <Descriptions.Item label="速率">{detailRow.su_lv} mL/h</Descriptions.Item>
            <Descriptions.Item label="时长">{detailRow.total_time} s</Descriptions.Item>
            <Descriptions.Item label="实际药量">{detailRow.real_dose || '-'} mL</Descriptions.Item>
            <Descriptions.Item label="开始时间">{detailRow.started_at}</Descriptions.Item>
            <Descriptions.Item label="结束时间">{detailRow.ended_at || '-'}</Descriptions.Item>
            <Descriptions.Item label="备注" span={2}>{detailRow.notes || '无'}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
}
