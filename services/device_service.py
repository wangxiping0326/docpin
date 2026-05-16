# 设备管理 - 串口检测 + 模拟模式切换
import json
import threading
import random
import time
from datetime import datetime
from database import get_db

# 简单记录，不搞复杂
_dev_status = {
    "connected": False,
    "sim_mode": True,  # 没有真硬件就模拟
    "com_port": "",
    "devices": [],
    "last_data_time": None,
    "serial_errors": 0,
}

# 模拟数据用的后台线程
_sim_thread = None
_sim_running = False

def scan_ports():
    """扫一下有没有串口设备"""
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        return [{"device": p.device, "name": p.name, "description": p.description} for p in ports]
    except Exception:
        # 没装 pyserial 或者没有串口
        return []

def _sim_device_data():
    """后台模拟设备回传数据 - 如果连接了模拟设备就跑"""
    global _sim_running
    while _sim_running:
        time.sleep(2)
        # 模拟设备心跳，更新最后数据时间
        _dev_status["last_data_time"] = datetime.now().isoformat()
        # 随机模拟设备状态变更
        if _dev_status["devices"]:
            # 随机挑一个设备更新状态
            pass  # 实际数据更新在 injection_service 里做

def init_device():
    """启动时调一次"""
    ports = scan_ports()
    if ports:
        _dev_status["connected"] = True
        _dev_status["sim_mode"] = False
        _dev_status["com_port"] = ports[0]["device"]
        print(f"[DEV] 发现串口: {ports[0]['device']} ({ports[0]['name']})")
    else:
        _dev_status["connected"] = False
        _dev_status["sim_mode"] = True
        _dev_status["com_port"] = ""
        print("[DEV] 没有串口，切到模拟模式")

    # 加载已注册的设备
    _load_devices()

    # 模拟模式下启动心跳线程
    global _sim_thread, _sim_running
    if _dev_status["sim_mode"] and not _sim_running:
        _sim_running = True
        _sim_thread = threading.Thread(target=_sim_device_data, daemon=True)
        _sim_thread.start()
        print("[DEV] 模拟设备心跳已启动")

def _load_devices():
    db = get_db()
    rows = db.execute("SELECT * FROM devices ORDER BY registered_at DESC").fetchall()
    _dev_status["devices"] = [dict(r) for r in rows]

def get_device_status():
    return dict(_dev_status)

def is_sim_mode():
    return _dev_status["sim_mode"]

def reg_device(uid: str, name: str = ""):
    """注册新注射器"""
    db = get_db()
    # 先检查是否重复
    exist = db.execute("SELECT COUNT(*) as c FROM devices WHERE device_uid=?", (uid,)).fetchone()
    if exist["c"] > 0:
        return False, f"设备 {uid} 已经注册过了"

    try:
        db.execute("INSERT INTO devices (device_uid, dev_name, status) VALUES (?, ?, 'offline')",
                   (uid, name or uid))
        db.commit()
        _load_devices()
        print(f"[DEV] 新设备注册: {uid}")
        return True, "注册成功"
    except Exception as e:
        return False, f"注册失败: {e}"

def update_dev_status(uid: str, status: str):
    """更新设备在线状态"""
    db = get_db()
    db.execute("UPDATE devices SET status=?, last_seen=CURRENT_TIMESTAMP WHERE device_uid=?",
               (status, uid))
    db.commit()
    _load_devices()

def connect_dev(uid: str):
    """连接指定设备"""
    # 更新状态为在线
    update_dev_status(uid, "online")
    if _dev_status["sim_mode"]:
        _dev_status["connected"] = True
    print(f"[DEV] 设备 {uid} 已连接")
    return True

def disconnect_dev(uid: str):
    """断开设备"""
    update_dev_status(uid, "offline")
    print(f"[DEV] 设备 {uid} 已断开")
    return True

def delete_device(uid: str):
    """删除设备注册"""
    db = get_db()
    db.execute("DELETE FROM devices WHERE device_uid=?", (uid,))
    db.commit()
    _load_devices()
    return True

def get_device_by_uid(uid: str):
    """查单个设备信息"""
    db = get_db()
    row = db.execute("SELECT * FROM devices WHERE device_uid=?", (uid,)).fetchone()
    return dict(row) if row else None

def count_online_devices():
    """统计在线设备数"""
    db = get_db()
    row = db.execute("SELECT COUNT(*) as c FROM devices WHERE status IN ('online', 'working')").fetchone()
    return row["c"] if row else 0

def check_device_health():
    """检查设备健康状态 - 模拟"""
    db = get_db()
    # 超过 60 秒没数据的标记为离线
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
