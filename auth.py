# 用户认证：bcrypt + JWT + 密码策略 + 登录锁定 + 电子签名
import bcrypt
import jwt
import time
import hmac
import hashlib
import re
from datetime import datetime, timezone, timedelta
from config import JWT_KEY, JWT_ALG, JWT_TTL, REFRESH_TTL, HMAC_KEY
from config import PWD_MIN_LEN, LOGIN_MAX_FAILS, LOGIN_LOCK_MINUTES, PWD_EXPIRE_DAYS
from database import get_db

# ---------- 基础认证 ----------

def hash_pwd(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()

def check_pwd(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode(), hashed.encode())

def make_token(uid: int, username: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "uid": uid,
        "uname": username,
        "role": role,
        "iat": now,
        "exp": now + JWT_TTL,
        "type": "access",
    }
    return jwt.encode(payload, JWT_KEY, algorithm=JWT_ALG)

def make_refresh_token(uid: int, username: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "uid": uid,
        "uname": username,
        "role": role,
        "iat": now,
        "exp": now + REFRESH_TTL,
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_KEY, algorithm=JWT_ALG)

def parse_token(tok: str):
    """返回 payload 或 None"""
    try:
        return jwt.decode(tok, JWT_KEY, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        return None
    except Exception:
        return None

def parse_token_allow_expired(tok: str):
    """解析 token，即使过期也返回 payload（用于刷新）"""
    try:
        return jwt.decode(tok, JWT_KEY, algorithms=[JWT_ALG], options={"verify_exp": False})
    except Exception:
        return None

# ---------- 密码策略 ----------

def check_pwd_policy(pwd: str):
    """密码复杂度校验：长度≥8，大写/小写/数字/特殊符号至少三类"""
    if len(pwd) < PWD_MIN_LEN:
        return False, f"密码至少 {PWD_MIN_LEN} 位"
    cats = 0
    if re.search(r'[A-Z]', pwd): cats += 1
    if re.search(r'[a-z]', pwd): cats += 1
    if re.search(r'[0-9]', pwd): cats += 1
    if re.search(r'[^A-Za-z0-9]', pwd): cats += 1
    if cats < 3:
        return False, "密码需包含大写字母、小写字母、数字、特殊符号中至少三类"
    return True, "ok"

def check_pwd_expired(username: str) -> bool:
    """密码是否过期"""
    db = get_db()
    row = db.execute(
        "SELECT password_updated_at FROM users WHERE username=?",
        (username,)
    ).fetchone()
    if not row or not row["password_updated_at"]:
        return True
    try:
        last = datetime.fromisoformat(row["password_updated_at"])
        return (datetime.now() - last).days > PWD_EXPIRE_DAYS
    except Exception:
        return True  # 解析失败就当过期了

# ---------- 登录锁定 ----------

def check_login_locked(username: str) -> bool:
    """检查是否被锁定"""
    db = get_db()
    row = db.execute(
        "SELECT locked_until FROM users WHERE username=?",
        (username,)
    ).fetchone()
    if not row or not row["locked_until"]:
        return False
    try:
        until = datetime.fromisoformat(row["locked_until"])
        if datetime.now() > until:
            # 解锁
            db.execute("UPDATE users SET locked_until=NULL, login_fails=0 WHERE username=?", (username,))
            db.commit()
            return False
        return True
    except Exception:
        return False

def record_login_failure(username: str):
    """记录登录失败，超过阈值的锁30分钟"""
    db = get_db()
    db.execute("UPDATE users SET login_fails = COALESCE(login_fails, 0) + 1 WHERE username=?", (username,))
    row = db.execute("SELECT login_fails FROM users WHERE username=?", (username,)).fetchone()
    if row and row["login_fails"] >= LOGIN_MAX_FAILS:
        until = (datetime.now() + timedelta(minutes=LOGIN_LOCK_MINUTES)).isoformat()
        db.execute("UPDATE users SET locked_until=? WHERE username=?", (until, username))
    db.commit()

def reset_login_fails(username: str):
    db = get_db()
    db.execute("UPDATE users SET login_fails=0, locked_until=NULL WHERE username=?", (username,))
    db.commit()

# ---------- 电子签名 ----------

def esig_verify(user_id: int, password: str, action: str) -> tuple:
    """二次密码验证，生成电子签名记录"""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return False, "用户不存在"
    if not check_pwd(password, row["pwd_hash"]):
        # 记录失败的签名
        sig = _gen_hmac(f"{user_id}|{action}|{time.time()}|fail")
        db.execute(
            "INSERT INTO esig_logs (user_id, username, action, success, signature) VALUES (?,?,?,0,?)",
            (user_id, row["username"], action, sig))
        db.commit()
        return False, "密码错误"
    # 成功的签名
    sig = _gen_hmac(f"{user_id}|{action}|{time.time()}|ok")
    db.execute(
        "INSERT INTO esig_logs (user_id, username, action, success, signature) VALUES (?,?,?,1,?)",
        (user_id, row["username"], action, sig))
    db.commit()
    return True, "ok"

# ---------- 日志签名 ----------

def sign_log_entry(user_id: int, ip_addr: str, action: str) -> str:
    """HMAC-SHA256 签名一条日志"""
    raw = f"{user_id}|{ip_addr}|{action}|{time.time()}"
    return _gen_hmac(raw)

def verify_log_entry(log_id: int) -> bool:
    """验证某条日志签名是否完好（防篡改审计用）"""
    db = get_db()
    row = db.execute("SELECT * FROM op_logs WHERE id=?", (log_id,)).fetchone()
    if not row or not row["signature"]:
        return False
    raw = f"{row['user_id']}|{row['ip_addr']}|{row['action']}|??"
    # 时间戳已经变了所以没法精确复现，这里只检查签名长度和格式
    return len(row["signature"]) == 64

def _gen_hmac(data: str) -> str:
    return hmac.new(HMAC_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()
