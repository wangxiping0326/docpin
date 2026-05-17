# 登录/用户相关路由 - 加了刷新、电子签名、改密码
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import (
    hash_pwd, check_pwd, make_token, make_refresh_token,
    parse_token, parse_token_allow_expired,
    check_pwd_policy, check_pwd_expired, check_login_locked,
    record_login_failure, reset_login_fails,
    esig_verify, sign_log_entry, verify_log_entry,
)
from datetime import datetime

router = APIRouter(prefix="/api", tags=["auth"])

def _get_user_from_req(req: Request):
    """从 Header 里扒 token 并解析，过期也算失败"""
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "没 token 别访问")
    tok = auth[7:]
    payload = parse_token(tok)
    if not payload:
        raise HTTPException(401, "token 过期或不对")
    return payload

# ---------- 登录 ----------

@router.post("/login")
async def do_login(req: Request):
    data = await req.json()
    uname = data.get("username", "").strip()
    pwd = data.get("password", "")

    # 检查锁定
    if check_login_locked(uname):
        raise HTTPException(423, "账号已被锁定，30分钟后再试")

    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username=? AND is_active=1", (uname,)).fetchone()
    if not row:
        record_login_failure(uname)
        raise HTTPException(400, "用户名或密码不对")

    if not check_pwd(pwd, row["pwd_hash"]):
        record_login_failure(uname)
        raise HTTPException(400, "用户名或密码不对")

    # 登录成功
    reset_login_fails(uname)
    tok = make_token(row["id"], row["username"], row["role"])
    refresh_tok = make_refresh_token(row["id"], row["username"], row["role"])
    token_payload = parse_token(tok)

    # 检查密码是否过期
    pwd_expired = check_pwd_expired(uname)

    # 记操作日志（带签名）
    client_ip = req.client.host if req.client else ""
    sig = sign_log_entry(row["id"], client_ip, "登录")
    db.execute(
        "INSERT INTO op_logs (user_id, username, action, ip_addr, signature) VALUES (?,?,?,?,?)",
        (row["id"], uname, "登录", client_ip, sig))
    db.commit()

    return {
        "token": tok,
        "refresh_token": refresh_tok,
        "token_exp": token_payload["exp"] if token_payload else 0,
        "user": {"id": row["id"], "username": row["username"], "role": row["role"]},
        "pwd_expired": pwd_expired,
    }

# ---------- Token 刷新 ----------

@router.post("/auth/refresh")
async def refresh_token(req: Request):
    """用 refresh_token 换新的 access token"""
    data = await req.json()
    refresh_tok = data.get("refresh_token", "")
    payload = parse_token_allow_expired(refresh_tok)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(401, "refresh_token 无效")
    new_tok = make_token(payload["uid"], payload["uname"], payload["role"])
    new_payload = parse_token(new_tok)
    return {
        "token": new_tok,
        "token_exp": new_payload["exp"] if new_payload else 0,
    }

# ---------- 电子签名 ----------

@router.post("/auth/esig")
async def do_esig(req: Request):
    """关键操作前的二次密码验证"""
    user = _get_user_from_req(req)
    data = await req.json()
    action = data.get("action", "unknown")
    pwd = data.get("password", "")
    ok, msg = esig_verify(user["uid"], pwd, action)
    if not ok:
        raise HTTPException(403, msg)
    return {"ok": True, "msg": "电子签名已记录"}

# ---------- 修改密码 ----------

@router.post("/auth/change-pwd")
async def change_password(req: Request):
    user = _get_user_from_req(req)
    data = await req.json()
    old_pwd = data.get("old_password", "")
    new_pwd = data.get("new_password", "")

    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (user["uid"],)).fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")
    if not check_pwd(old_pwd, row["pwd_hash"]):
        raise HTTPException(400, "旧密码不对")

    ok, msg = check_pwd_policy(new_pwd)
    if not ok:
        raise HTTPException(400, msg)

    new_hash = hash_pwd(new_pwd)
    now = datetime.now().isoformat()
    db.execute("UPDATE users SET pwd_hash=?, password_updated_at=? WHERE id=?",
               (new_hash, now, user["uid"]))
    db.commit()

    # 记日志
    client_ip = req.client.host if req.client else ""
    sig = sign_log_entry(user["uid"], client_ip, "修改密码")
    db.execute(
        "INSERT INTO op_logs (user_id, username, action, ip_addr, signature) VALUES (?,?,?,?,?)",
        (user["uid"], user["uname"], "修改密码", client_ip, sig))
    db.commit()

    return {"ok": True, "msg": "密码已更新，请重新登录"}

# ---------- 日志签名验证 ----------

@router.get("/auth/verify-log/{log_id}")
async def verify_log(log_id: int, req: Request):
    user = _get_user_from_req(req)
    if user["role"] != "admin":
        raise HTTPException(403, "admin only")
    valid = verify_log_entry(log_id)
    return {"log_id": log_id, "valid": valid}

# ---------- 用户信息 ----------

@router.get("/me")
async def get_me(req: Request):
    payload = _get_user_from_req(req)
    db = get_db()
    row = db.execute("SELECT id, username, role FROM users WHERE id=?", (payload["uid"],)).fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")
    return dict(row)

@router.get("/users")
async def list_users(req: Request):
    payload = _get_user_from_req(req)
    if payload["role"] != "admin":
        raise HTTPException(403, "只有 admin 能看")
    db = get_db()
    rows = db.execute(
        "SELECT id, username, role, is_active, login_fails, locked_until, created_at FROM users ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]

@router.post("/users")
async def add_user(req: Request):
    payload = _get_user_from_req(req)
    if payload["role"] != "admin":
        raise HTTPException(403, "只有 admin 能加用户")
    data = await req.json()
    uname = data.get("username", "").strip()
    pwd = data.get("password", "").strip()
    role = data.get("role", "operator")
    if not uname or not pwd:
        raise HTTPException(400, "用户名密码不能空")
    ok, msg = check_pwd_policy(pwd)
    if not ok:
        raise HTTPException(400, msg)
    db = get_db()
    now = datetime.now().isoformat()
    try:
        db.execute(
            "INSERT INTO users (username, pwd_hash, role, password_updated_at) VALUES (?, ?, ?, ?)",
            (uname, hash_pwd(pwd), role, now))
        db.commit()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, f"创建失败: {e}")

@router.delete("/users/{uid}")
async def del_user(uid: int, req: Request):
    payload = _get_user_from_req(req)
    if payload["role"] != "admin":
        raise HTTPException(403, "只有 admin 能删")
    db = get_db()
    db.execute("DELETE FROM users WHERE id=? AND role!='admin'", (uid,))
    db.commit()
    return {"ok": True}
