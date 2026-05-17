# 设备管理 - 协议栈集成 + 重发队列 + 心跳检测
import json
import threading
import random
import time
from datetime import datetime
from database import get_db
from config import CMD_TIMEOUT, CMD_MAX_RETRIES, HEARTBEAT_INTERVAL, HEARTBEAT_MISS_MAX

_dev_status = {
    "connected": False, "sim_mode": True, "com_port": "",
    "devices": [], "last_data_time": None, "serial_errors": 0,
}

# 协议层对象
_virtual_dev = None
_protocol_ready = False

# 待确认指令队列
_pending_commands = {}
_pending_lock = threading.Lock()
_cmd_id_seq = 0

# 心跳线程
_heartbeat_thread = None
_heartbeat_running = False
_heartbeat_missed = 0

# rx 数据缓冲
_rx_buffer = b""

def _get_protocol():
    from services import protocol
    return protocol

# ---------- 帧收发 ----------

def send_frame_and_wait(frame: bytes, expect_cmd=None, timeout=None):
    """发一帧并等待应答，返回 parsed dict 或 None"""
    if timeout is None:
        timeout = CMD_TIMEOUT

    protocol = _get_protocol()
    from services.serial_sim import get_virtual_device

    vd = get_virtual_device()
    if vd is None:
        return None

    # 喂给模拟硬件
    vd.feed_bytes(frame)

    # 等待应答
    deadline = time.time() + timeout
    while time.time() < deadline:
        tx = vd.pop_tx()
        if tx:
            try:
                parsed = protocol.unpack(tx)
                if expect_cmd is None or parsed["cmd"] == expect_cmd:
                    return parsed
                # 如果不是期望的命令，继续等
            except protocol.ProtocolError:
                continue
        time.sleep(0.01)

    return None  # 超时

def send_with_retry(frame: bytes, expect_cmd=None) -> dict:
    """发帧 + 自动重试（最多 CMD_MAX_RETRIES 次），返回 {'ok': bool, 'data': parsed|None, 'retries': int}"""
    protocol = _get_protocol()
    for attempt in range(CMD_MAX_RETRIES + 1):
        resp = send_frame_and_wait(frame, expect_cmd, CMD_TIMEOUT)
        if resp:
            return {"ok": True, "data": resp, "retries": attempt}

    # 全部失败 → 记录通信超时报警
    _dev_status["serial_errors"] += 1
    db = get_db()
    db.execute(
        "INSERT INTO alarms (injection_id, alarm_level, msg, yali_val, yao_val) VALUES (NULL, 'jiting', ?, 0, 0)",
        (f"通信超时: 重试{CMD_MAX_RETRIES}次无应答",))
    db.commit()

    return {"ok": False, "data": None, "retries": CMD_MAX_RETRIES}

# ---------- 心跳 ----------

def _heartbeat_loop(ws_pool=None):
    """后台心跳线程"""
    global _heartbeat_missed, _heartbeat_running
    protocol = _get_protocol()
    from services.serial_sim import get_virtual_device

    while _heartbeat_running:
        time.sleep(HEARTBEAT_INTERVAL)
        if not _heartbeat_running:
            break

        vd = get_virtual_device()
        if vd is None:
            continue

        # 发送心跳帧
        hb = protocol.pack_heart()
        resp = send_frame_and_wait(hb, protocol.CMD_HEART_ACK, CMD_TIMEOUT)

        if resp:
            _heartbeat_missed = 0
            _dev_status["last_data_time"] = datetime.now().isoformat()
        else:
            _heartbeat_missed += 1
            if _heartbeat_missed >= HEARTBEAT_MISS_MAX:
                # 连续3次无心跳 → 设备离线 → 紧急停注
                print(f"[DEV] 心跳丢失{_heartbeat_missed}次，判定离线，触发紧急停注")
                _dev_status["connected"] = False
                from services.injection_service import stop_injection
                stop_injection("system", force=True)
                # 报警
                db = get_db()
                db.execute(
                    "INSERT INTO alarms (injection_id, alarm_level, msg, yali_val, yao_val) VALUES (NULL, 'jiting', ?, 0, 0)",
                    ("设备离线 - 连续3次心跳无应答",))
                db.commit()
                if ws_pool:
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                    asyncio.run_coroutine_threadsafe(
                        ws_pool.blast({
                            "type": "alarm",
                            "data": {"level": "jiting", "msg": "设备离线！连续3次心跳无应答，已紧急停注"}
                        }), loop)

# ---------- 初始化 ----------

def scan_ports():
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        return [{"device": p.device, "name": p.name, "description": p.description} for p in ports]
    except Exception:
        return []

def init_device(ws_pool=None):
    global _protocol_ready, _heartbeat_running, _heartbeat_thread, _virtual_dev, _heartbeat_missed
    protocol = _get_protocol()
    from services.serial_sim import get_virtual_device

    ports = scan_ports()
    if ports:
        _dev_status["connected"] = True
        _dev_status["sim_mode"] = False
        _dev_status["com_port"] = ports[0]["device"]
        print(f"[DEV] 发现串口: {ports[0]['device']}")
        _protocol_ready = True
    else:
        _dev_status["connected"] = False
        _dev_status["sim_mode"] = True
        _dev_status["com_port"] = ""
        _protocol_ready = True
        print("[DEV] 模拟模式 - 使用 VirtualInjector")

    # 初始化虚拟设备
    _virtual_dev = get_virtual_device()

    # 启动心跳
    if not _heartbeat_running:
        _heartbeat_running = True
        _heartbeat_missed = 0
        _heartbeat_thread = threading.Thread(
            target=_heartbeat_loop, args=(ws_pool,), daemon=True)
        _heartbeat_thread.start()
        print("[DEV] 心跳线程已启动")

    _load_devices()

def _load_devices():
    db = get_db()
    rows = db.execute("SELECT * FROM devices ORDER BY registered_at DESC").fetchall()
    _dev_status["devices"] = [dict(r) for r in rows]

def get_device_status():
    return dict(_dev_status)

def is_sim_mode():
    return _dev_status["sim_mode"]

def get_virtual_device():
    """获取协议模拟器实例（供外部使用）"""
    global _virtual_dev
    if _virtual_dev is None:
        from services.serial_sim import get_virtual_device as _gvd
        _virtual_dev = _gvd()
    return _virtual_dev

# ---------- 设备CRUD ----------

def reg_device(uid: str, name: str = ""):
    db = get_db()
    exist = db.execute("SELECT COUNT(*) as c FROM devices WHERE device_uid=?", (uid,)).fetchone()
    if exist["c"] > 0:
        return False, f"设备 {uid} 已注册"
    try:
        db.execute("INSERT INTO devices (device_uid, dev_name, status) VALUES (?, ?, 'offline')", (uid, name or uid))
        db.commit()
        _load_devices()
        return True, "ok"
    except Exception as e:
        return False, str(e)

def update_dev_status(uid: str, status: str):
    db = get_db()
    db.execute("UPDATE devices SET status=?, last_seen=CURRENT_TIMESTAMP WHERE device_uid=?", (status, uid))
    db.commit()
    _load_devices()

def connect_dev(uid: str):
    update_dev_status(uid, "online")
    if _dev_status["sim_mode"]:
        _dev_status["connected"] = True
    return True

def disconnect_dev(uid: str):
    update_dev_status(uid, "offline")
    return True

def delete_device(uid: str):
    db = get_db()
    db.execute("DELETE FROM devices WHERE device_uid=?", (uid,))
    db.commit()
    _load_devices()
    return True

def get_device_by_uid(uid: str):
    db = get_db()
    row = db.execute("SELECT * FROM devices WHERE device_uid=?", (uid,)).fetchone()
    return dict(row) if row else None

def count_online_devices():
    db = get_db()
    row = db.execute("SELECT COUNT(*) as c FROM devices WHERE status IN ('online', 'working')").fetchone()
    return row["c"] if row else 0

def check_device_health():
    db = get_db()
    rows = db.execute("SELECT * FROM devices WHERE status='online'").fetchall()
    warnings = []
    for r in rows:
        if r["last_seen"]:
            try:
                last = datetime.fromisoformat(r["last_seen"])
                if (datetime.now() - last).total_seconds() > 60:
                    update_dev_status(r["device_uid"], "offline")
                    warnings.append(f"设备 {r['device_uid']} 超时离线")
            except Exception:
                pass
    return warnings
