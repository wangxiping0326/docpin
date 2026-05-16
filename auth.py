# 用户认证：bcrypt + JWT，简单粗暴
import bcrypt
import jwt
import time
from datetime import datetime, timezone
from config import JWT_KEY, JWT_ALG, JWT_TTL

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
        "exp": now + JWT_TTL
    }
    return jwt.encode(payload, JWT_KEY, algorithm=JWT_ALG)

def parse_token(tok: str):
    """返回 payload 或 None"""
    try:
        return jwt.decode(tok, JWT_KEY, algorithms=[JWT_ALG])
    except Exception:
        return None
