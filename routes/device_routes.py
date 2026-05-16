# 设备管理路由
from fastapi import APIRouter, Request, HTTPException
from routes.auth_routes import _get_user_from_req
from services.device_service import (
    get_device_status, reg_device, connect_dev, disconnect_dev,
    init_device, scan_ports, delete_device, check_device_health,
    count_online_devices, get_device_by_uid,
)

router = APIRouter(prefix="/api/device", tags=["device"])

@router.get("/status")
async def dev_status(req: Request):
    _get_user_from_req(req)
    st = get_device_status()
    st["online_count"] = count_online_devices()
    return st

@router.get("/ports")
async def list_ports(req: Request):
    _get_user_from_req(req)
    ports = scan_ports()
    return {"ports": ports, "count": len(ports)}

@router.post("/register")
async def register_dev(req: Request):
    payload = _get_user_from_req(req)
    if payload["role"] != "admin":
        raise HTTPException(403, "只有管理员能注册设备")
    data = await req.json()
    uid = data.get("uid", "").strip()
    name = data.get("name", "")
    if not uid:
        raise HTTPException(400, "设备ID不能空")
    ok, msg = reg_device(uid, name)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "msg": msg}

@router.post("/connect")
async def connect_device(req: Request):
    _get_user_from_req(req)
    data = await req.json()
    uid = data.get("uid", "")
    if not uid:
        raise HTTPException(400, "uid 不能空")
    ok = connect_dev(uid)
    return {"ok": ok}

@router.post("/disconnect")
async def disconnect_device(req: Request):
    _get_user_from_req(req)
    data = await req.json()
    uid = data.get("uid", "")
    if not uid:
        raise HTTPException(400, "uid 不能空")
    ok = disconnect_dev(uid)
    return {"ok": ok}

@router.delete("/{uid}")
async def remove_device(uid: str, req: Request):
    payload = _get_user_from_req(req)
    if payload["role"] != "admin":
        raise HTTPException(403, "admin only")
    ok = delete_device(uid)
    return {"ok": ok}

@router.get("/detail/{uid}")
async def device_detail(uid: str, req: Request):
    _get_user_from_req(req)
    dev = get_device_by_uid(uid)
    if not dev:
        raise HTTPException(404, "设备不存在")
    return dev

@router.get("/health")
async def health_check(req: Request):
    _get_user_from_req(req)
    warnings = check_device_health()
    return {"warnings": warnings, "ok": len(warnings) == 0}
