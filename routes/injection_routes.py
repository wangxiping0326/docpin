# 注射控制路由
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from services.injection_service import (
    get_shot_state, start_injection, stop_injection, get_yao_recommend
)
from routes.auth_routes import _get_user_from_req
import json
from datetime import datetime

router = APIRouter(prefix="/api/shot", tags=["injection"])

def get_ws_pool():
    from ws_manager import ws_pool
    return ws_pool

@router.post("/start")
async def start_shot(req: Request):
    user = _get_user_from_req(req)
    data = await req.json()
    ok, msg = start_injection(data, user["uname"], get_ws_pool())
    if not ok:
        raise HTTPException(400, msg)

    # 记日志
    db = get_db()
    db.execute("INSERT INTO op_logs (user_id, username, action, ip_addr) VALUES (?,?,?,?)",
               (user["uid"], user["uname"], f"启动注射 {data.get('mode')}", ""))
    db.commit()

    # 广播给所有人
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(get_ws_pool().blast({
            "type": "shot_started",
            "data": {"mode": data.get("mode"), "by": user["uname"]}
        }))
        loop.create_task(get_ws_pool().blast({
            "type": "notification",
            "data": {"level": "info", "msg": f"注射已开始 by {user['uname']}"}
        }))
    except Exception:
        pass

    return {"ok": True, "msg": msg}

@router.post("/stop")
async def stop_shot(req: Request):
    user = _get_user_from_req(req)
    ok, msg = stop_injection(user["uname"])
    if not ok:
        raise HTTPException(400, msg)

    db = get_db()
    db.execute("INSERT INTO op_logs (user_id, username, action, ip_addr) VALUES (?,?,?,?)",
               (user["uid"], user["uname"], "停止注射", ""))
    db.commit()

    import asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(get_ws_pool().blast({
            "type": "shot_stopped",
            "data": {"by": user["uname"]}
        }))
        loop.create_task(get_ws_pool().blast({
            "type": "notification",
            "data": {"level": "warning", "msg": f"注射被 {user['uname']} 停止了"}
        }))
    except Exception:
        pass

    return {"ok": True, "msg": msg}

@router.get("/status")
async def shot_status():
    return get_shot_state()

@router.get("/recommend")
async def yaoliang_recommend(req: Request):
    user = _get_user_from_req(req)
    val = get_yao_recommend(user["uid"])
    return val

@router.get("/history")
async def shot_history(
    req: Request,
    page: int = 1,
    page_size: int = 20,
    start_d: str = "",
    end_d: str = "",
    mode: str = "",
):
    _get_user_from_req(req)
    db = get_db()
    sql = "SELECT i.*, u.username FROM injections i LEFT JOIN users u ON i.user_id = u.id WHERE 1=1"
    params = []

    if start_d:
        sql += " AND i.started_at >= ?"
        params.append(start_d)
    if end_d:
        sql += " AND i.started_at <= ?"
        params.append(end_d)
    if mode:
        sql += " AND i.shot_mode = ?"
        params.append(mode)

    count_sql = sql.replace("SELECT i.*, u.username", "SELECT COUNT(*) as c")
    total = db.execute(count_sql, params).fetchone()["c"]

    sql += " ORDER BY i.started_at DESC LIMIT ? OFFSET ?"
    params.extend([page_size, (page - 1) * page_size])
    rows = db.execute(sql, params).fetchall()

    return {"list": [dict(r) for r in rows], "total": total}
