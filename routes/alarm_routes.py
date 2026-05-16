# 报警相关路由
from fastapi import APIRouter, Request, HTTPException
from routes.auth_routes import _get_user_from_req
from services.alarm_service import (
    get_alarms, get_alarm_stats, _get_thresholds, set_threshold,
    mark_alarm_handled, get_unhandled_alarms, get_alarm_count_today,
    get_alarm_count_by_level,
)
from services.injection_service import get_latest_alarms
from database import get_db

router = APIRouter(prefix="/api/alarm", tags=["alarm"])

@router.get("/list")
async def alarm_list(
    req: Request,
    page: int = 1,
    page_size: int = 20,
    level: str = "",
    start_d: str = "",
    end_d: str = "",
):
    _get_user_from_req(req)
    return get_alarms(page, page_size, level or None, start_d or None, end_d or None)

@router.get("/stats")
async def alarm_stats(req: Request):
    _get_user_from_req(req)
    return get_alarm_stats()

@router.get("/latest")
async def latest_alarms(req: Request, limit: int = 5):
    """最新的N条报警"""
    _get_user_from_req(req)
    return get_latest_alarms(limit)

@router.get("/unhandled")
async def unhandled_alarms(req: Request):
    """未处理的报警"""
    _get_user_from_req(req)
    return get_unhandled_alarms()

@router.get("/today_count")
async def today_alarm_count(req: Request):
    _get_user_from_req(req)
    return {
        "total": get_alarm_count_today(),
        "warn1": get_alarm_count_by_level("warn1", 1),
        "warn2": get_alarm_count_by_level("warn2", 1),
        "jiting": get_alarm_count_by_level("jiting", 1),
    }

@router.post("/handle/{alarm_id}")
async def handle_alarm(alarm_id: int, req: Request):
    """标记报警已处理"""
    _get_user_from_req(req)
    mark_alarm_handled(alarm_id)
    return {"ok": True, "msg": f"报警 #{alarm_id} 已标记为处理"}

@router.get("/thresholds")
async def get_thresholds(req: Request):
    _get_user_from_req(req)
    return _get_thresholds()

@router.put("/thresholds")
async def update_thresholds(req: Request):
    payload = _get_user_from_req(req)
    if payload["role"] != "admin":
        raise HTTPException(403, "只有 admin 能改阈值")
    data = await req.json()
    db = get_db()
    for k, v in data.items():
        db.execute("INSERT OR REPLACE INTO settings (skey, sval) VALUES (?, ?)", (k, str(v)))
    db.commit()
    return {"ok": True, "msg": "阈值已更新"}

@router.put("/thresholds/single")
async def update_single_threshold(req: Request):
    """更新单个阈值"""
    payload = _get_user_from_req(req)
    if payload["role"] != "admin":
        raise HTTPException(403, "admin only")
    data = await req.json()
    key = data.get("key", "")
    val = float(data.get("value", 0))
    if not key or not key.startswith("thresh_"):
        raise HTTPException(400, "无效的阈值key")
    set_threshold(key, val)
    return {"ok": True}
