# docpin - 高精度智能电子注射器管控系统

## 快速启动

### 1. 安装后端依赖
```bash
pip install -r requirements.txt
```

### 2. 构建前端
```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. 启动
```bash
python main.py
```

### 4. 访问
浏览器打开 `http://localhost:8000`

## 默认账号
- 管理员: `admin` / `admin123`
- 操作员: `op1` / `admin123`

## 技术栈
- 后端: Python 3.10+ / FastAPI / SQLite / WebSocket
- 前端: React 18 / antd 5 / recharts
- 串口模拟: pyserial (无真实硬件时自动切为模拟模式)

## 功能概览
- 四种注射模式: 持续输注、间歇输注、按需推注、自定义曲线
- 三级压力报警 + 紧急停注
- 实时 WebSocket 推送 + 多终端协同
- 用药数据管理 + 统计图表 + Excel 导出
- 设备管理 + 串口检测 + 模拟模式
- 用户权限(RBAC) + 操作日志
