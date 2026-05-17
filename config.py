# 系统配置 - 优先读环境变量，没有就临时随机（仅开发）
import os
import secrets

# JWT 和 HMAC 从环境变量拿，没有就随机生成并警告
_JWT_ENV = os.environ.get("JWT_SECRET", "")
_HMAC_ENV = os.environ.get("HMAC_KEY", "")

if not _JWT_ENV:
    _JWT_ENV = secrets.token_hex(32)
    print("[CONFIG] !!! JWT_SECRET 未设置！已用随机值（重启后 token 全部失效）")
if not _HMAC_ENV:
    _HMAC_ENV = secrets.token_hex(32)
    print("[CONFIG] !!! HMAC_KEY 未设置！已用随机值（重启后签名验证失效）")

JWT_KEY = _JWT_ENV
JWT_ALG = "HS256"
JWT_TTL = int(os.environ.get("JWT_TTL", "900"))        # 默认15分钟
REFRESH_TTL = int(os.environ.get("REFRESH_TTL", "7200"))  # 刷新token 2小时

HMAC_KEY = _HMAC_ENV

# 数据库
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data.db"))

# 默认的三级报警阈值
DEFAULT_THRESHOLDS = {
    "yalijiance": 80.0,
    "yaol_warn": 95.0,
    "jiting_val": 100.0,
}

# 模拟数据生成参数
SIM_INTERVAL = 1.0
SIM_PRESSURE_BASE = 50.0
SIM_YAOLIANG_START = 10.0
SIM_YAOLIANG_RATE = 0.02

# 注射模式
SHOT_MODES = ["cont", "jianxie", "tui", "custom"]

# 协议参数
CMD_TIMEOUT = 0.5     # 500ms 应答超时
CMD_MAX_RETRIES = 3   # 最多重试3次
HEARTBEAT_INTERVAL = 1.0   # 心跳间隔1秒
HEARTBEAT_MISS_MAX = 3     # 连续3次无心跳 = 离线

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "build")

# API 文档（生产环境可关）
SHOW_DOCS = os.environ.get("SHOW_DOCS", "true").lower() == "true"

# 密码策略
PWD_MIN_LEN = 8
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_MINUTES = 30
PWD_EXPIRE_DAYS = 90
