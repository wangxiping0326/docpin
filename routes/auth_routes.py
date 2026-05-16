# 登录/用户相关路由
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import hash_pwd, check_pwd, make_token, parse_token

router = APIRouter(prefix="/api", tags=["auth"])

def _get_user_from_req(req: Request):
    """从 Header 里扒拉 token 并解析"""
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "没 token 别访问")
    tok = auth[7:]
    payload = parse_token(tok)
    if not payload:
        raise HTTPException(401, "token 过期或不对")
    return payload

@router.post("/login")
async def do_login(req: Request):
    data = await req.json()
    uname = data.get("username", "").strip()
    pwd = data.get("password", "")

    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username=? AND is_active=1", (uname,)).fetchone()
    if not row:
        raise HTTPException(400, "用户名或密码不对")

    if not check_pwd(pwd, row["pwd_hash"]):
        raise HTTPException(400, "用户名或密码不对")

    tok = make_token(row["id"], row["username"], row["role"])

    # 记操作日志
    client_ip = req.client.host if req.client else ""
    db.execute("INSERT INTO op_logs (user_id, username, action, ip_addr) VALUES (?,?,?,?)",
               (row["id"], uname, "登录", client_ip))
    db.commit()

    return {"token": tok, "user": {"id": row["id"], "username": row["username"], "role": row["role"]}}

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
    rows = db.execute("SELECT id, username, role, is_active, created_at FROM users ORDER BY id").fetchall()
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
    db = get_db()
    try:
        db.execute("INSERT INTO users (username, pwd_hash, role) VALUES (?, ?, ?)",
                   (uname, hash_pwd(pwd), role))
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
