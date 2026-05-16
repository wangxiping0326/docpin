# db stuff - sqlite3 初始化，建表都在这里
import sqlite3
import os
from config import DB_PATH, DEFAULT_THRESHOLDS

_conn = None

def get_db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn

def init_db():
    """跑一次，建所有表 + 默认数据"""
    db = get_db()
    cur = db.cursor()

    # 用户表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            pwd_hash TEXT NOT NULL,
            role TEXT DEFAULT 'operator',  -- admin / operator
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 设备表 - 注射器
    cur.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_uid TEXT UNIQUE NOT NULL,
            dev_name TEXT DEFAULT '',
            status TEXT DEFAULT 'offline',  -- online / offline / working
            last_seen TIMESTAMP,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 注射记录表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS injections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            device_id INTEGER,
            shot_mode TEXT NOT NULL,
            su_lv REAL DEFAULT 0,        -- 速率
            ji_liang REAL DEFAULT 0,      -- 剂量
            total_time REAL DEFAULT 0,    -- 注射时长(秒)
            jian_ge REAL DEFAULT 0,       -- 间歇间隔
            real_dose REAL DEFAULT 0,     -- 实际注射药量
            status TEXT DEFAULT 'done',   -- running / stopped / done / jiting
            notes TEXT DEFAULT '',
            started_at TIMESTAMP,
            ended_at TIMESTAMP
        )
    """)

    # 报警记录
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            injection_id INTEGER,
            alarm_level TEXT NOT NULL,    -- warn1 / warn2 / jiting
            msg TEXT DEFAULT '',
            yali_val REAL DEFAULT 0,
            yao_val REAL DEFAULT 0,
            handled INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 操作日志
    cur.execute("""
        CREATE TABLE IF NOT EXISTS op_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT DEFAULT '',
            action TEXT DEFAULT '',
            ip_addr TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 系统设置 - kv 存储
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            skey TEXT PRIMARY KEY,
            sval TEXT DEFAULT ''
        )
    """)

    # 写入默认阈值
    import json
    default_settings = [
        ("thresh_yali_warn", str(DEFAULT_THRESHOLDS["yalijiance"])),
        ("thresh_yaol_warn", str(DEFAULT_THRESHOLDS["yaol_warn"])),
        ("thresh_jiting", str(DEFAULT_THRESHOLDS["jiting_val"])),
    ]
    for k, v in default_settings:
        cur.execute("INSERT OR IGNORE INTO settings (skey, sval) VALUES (?, ?)", (k, v))

    db.commit()

    # 首次启动：如果没有 admin 用户就创建默认的
    cur.execute("SELECT COUNT(*) as c FROM users WHERE role='admin'")
    row = cur.fetchone()
    if row["c"] == 0:
        import bcrypt
        pwd = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        cur.execute("INSERT INTO users (username, pwd_hash, role) VALUES (?, ?, ?)",
                    ("admin", pwd, "admin"))
        cur.execute("INSERT INTO users (username, pwd_hash, role) VALUES (?, ?, ?)",
                    ("op1", pwd, "operator"))
        db.commit()
        print("[DB] 默认用户已创建 admin / op1 密码都是 admin123")

    print("[DB] 数据库初始化完成")
