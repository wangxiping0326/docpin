# 系统配置 - 所有的常量、阈值都扔这儿了
import os
import json

# JWT
JWT_KEY = "docpin_injector_2024_x"
JWT_ALG = "HS256"
JWT_TTL = 24 * 3600  # 一天

# 数据库
DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")

# 默认的三级报警阈值
DEFAULT_THRESHOLDS = {
    "yalijiance": 80.0,   # 预警 pressure
    "yaol_warn": 95.0,    # 警告 yao liang
    "jiting_val": 100.0,  # 紧急停注
}

# 模拟数据生成参数
SIM_INTERVAL = 1.0  # 每秒刷一次
SIM_PRESSURE_BASE = 50.0
SIM_YAOLIANG_START = 10.0
SIM_YAOLIANG_RATE = 0.02  # 每秒消耗

# 注射模式
SHOT_MODES = ["cont", "jianxie", "tui", "custom"]
# cont = 持续输注, jianxie = 间歇输注, tui = 按需推注, custom = 自定义曲线

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "build")
