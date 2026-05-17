# db stuff - sqlite3 WAL模式 + 所有表
import sqlite3
import os
from config import DB_PATH, DEFAULT_THRESHOLDS

_conn = None

def get_db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        # WAL + busy_timeout
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.execute("PRAGMA busy_timeout=5000;")
    return _conn

def init_db():
    """跑一次，建所有表 + 默认数据"""
    db = get_db()
    cur = db.cursor()

    # 用户表 - 加了 locked_until, password_updated_at
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            pwd_hash TEXT NOT NULL,
            role TEXT DEFAULT 'operator',
            is_active INTEGER DEFAULT 1,
            login_fails INTEGER DEFAULT 0,
            locked_until TEXT,
            password_updated_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 设备表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_uid TEXT UNIQUE NOT NULL,
            dev_name TEXT DEFAULT '',
            status TEXT DEFAULT 'offline',
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
            su_lv REAL DEFAULT 0,
            ji_liang REAL DEFAULT 0,
            total_time REAL DEFAULT 0,
            jian_ge REAL DEFAULT 0,
            real_dose REAL DEFAULT 0,
            status TEXT DEFAULT 'done',
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
            alarm_level TEXT NOT NULL,
            msg TEXT DEFAULT '',
            yali_val REAL DEFAULT 0,
            yao_val REAL DEFAULT 0,
            handled INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 操作日志 - 加了 signature, archived（审计追溯，禁止物理删除）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS op_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT DEFAULT '',
            action TEXT DEFAULT '',
            ip_addr TEXT DEFAULT '',
            signature TEXT DEFAULT '',
            archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 系统设置
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            skey TEXT PRIMARY KEY,
            sval TEXT DEFAULT ''
        )
    """)

    # 设备状态持久化 - 断电恢复用（单行表）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS device_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            device_id TEXT NOT NULL DEFAULT '',
            is_running INTEGER NOT NULL DEFAULT 0,
            mode TEXT DEFAULT '',
            target_dose REAL DEFAULT 0,
            remaining_dose REAL DEFAULT 0,
            elapsed_seconds REAL DEFAULT 0,
            total_seconds REAL DEFAULT 0,
            yali_now REAL DEFAULT 0,
            start_time TEXT DEFAULT '',
            lock_token TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 电子签名记录
    cur.execute("""
        CREATE TABLE IF NOT EXISTS esig_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT DEFAULT '',
            action TEXT DEFAULT '',
            success INTEGER DEFAULT 0,
            signature TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 确保 device_state 有一行
    cur.execute("INSERT OR IGNORE INTO device_state (id, device_id) VALUES (1, '')")

    # 写入默认阈值
    default_settings = [
        ("thresh_yali_warn", str(DEFAULT_THRESHOLDS["yalijiance"])),
        ("thresh_yaol_warn", str(DEFAULT_THRESHOLDS["yaol_warn"])),
        ("thresh_jiting", str(DEFAULT_THRESHOLDS["jiting_val"])),
    ]
    for k, v in default_settings:
        cur.execute("INSERT OR IGNORE INTO settings (skey, sval) VALUES (?, ?)", (k, v))

    db.commit()

    # ---------- 迁移：给旧表加新字段（防止升级时报 no such column）----------
    migrations = [
        # users 表
        ("ALTER TABLE users ADD COLUMN login_fails INTEGER DEFAULT 0", "users.login_fails"),
        ("ALTER TABLE users ADD COLUMN locked_until TEXT", "users.locked_until"),
        ("ALTER TABLE users ADD COLUMN password_updated_at TEXT", "users.password_updated_at"),
        # op_logs 表
        ("ALTER TABLE op_logs ADD COLUMN signature TEXT DEFAULT ''", "op_logs.signature"),
        ("ALTER TABLE op_logs ADD COLUMN archived INTEGER DEFAULT 0", "op_logs.archived"),
    ]
    for sql, col_name in migrations:
        try:
            cur.execute(sql)
            db.commit()
            print(f"[DB] 迁移完成: {col_name}")
        except sqlite3.OperationalError:
            pass  # 列已存在

    # 首次启动：如果没有 admin 用户就创建默认的
    cur.execute("SELECT COUNT(*) as c FROM users WHERE role='admin'")
    row = cur.fetchone()
    if row["c"] == 0:
        import bcrypt
        from datetime import datetime
        pwd = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        now = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO users (username, pwd_hash, role, password_updated_at) VALUES (?, ?, ?, ?)",
            ("admin", pwd, "admin", now))
        cur.execute(
            "INSERT INTO users (username, pwd_hash, role, password_updated_at) VALUES (?, ?, ?, ?)",
            ("op1", pwd, "operator", now))
        db.commit()
        print("[DB] 默认用户已创建 admin / op1 密码都是 admin123")
        print("[DB] !!! 请在首次登录后立即修改密码！")

    print("[DB] 数据库初始化完成 (WAL模式)")
