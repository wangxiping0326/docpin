# 注射核心逻辑 - device_state持久化 + 协议帧 + 恢复
import threading
import time
import random
import math
import uuid
from datetime import datetime
from database import get_db
from services.alarm_service import check_alarms
from services.device_service import get_device_status, is_sim_mode

_shot_state = {
    "running": False, "mode": "", "su_lv": 0, "ji_liang": 0,
    "total": 0, "elapsed": 0, "remaining": 0,
    "yali_now": 50.0, "yao_left": 10.0,
    "started_by": "", "device_id": None, "record_id": None,
    "jiting": False, "paused": False,
    "curve_points": [], "jian_ge": 0, "jian_ge_left": 0,
    "lock_token": None,
}

_lock = threading.Lock()
_bg_thread = None
_curve_idx = 0

def get_shot_state():
    with _lock:
        return dict(_shot_state)

# ---------- device_state 持久化 ----------

def _persist_device_state():
    """把当前状态写入 device_state 表（WAL模式下高频写）"""
    with _lock:
        db = get_db()
        db.execute("""
            UPDATE device_state SET
                is_running=?, mode=?, target_dose=?, remaining_dose=?,
                elapsed_seconds=?, total_seconds=?, yali_now=?,
                lock_token=?, updated_at=datetime('now','localtime')
            WHERE id=1
        """, (
            1 if _shot_state["running"] else 0,
            _shot_state["mode"],
            _shot_state["ji_liang"],
            _shot_state["yao_left"],
            int(_shot_state["elapsed"]),
            int(_shot_state["total"]),
            _shot_state["yali_now"],
            _shot_state["lock_token"],
        ))
        db.commit()

def _clear_device_state():
    """清除运行状态"""
    db = get_db()
    db.execute("""
        UPDATE device_state SET is_running=0, lock_token=NULL,
        updated_at=datetime('now','localtime') WHERE id=1
    """)
    db.commit()

# ---------- 启动时状态恢复 ----------

def recover_state(ws_pool=None):
    """启动时读 device_state，尝试恢复"""
    db = get_db()
    row = db.execute("SELECT * FROM device_state WHERE id=1 AND is_running=1").fetchone()
    if not row:
        return  # 没有在跑的任务

    print("[RECOVER] 发现未完成的注射记录，尝试恢复...")

    # 尝试与硬件握手
    from services.protocol import pack_status_query, CMD_STATUS_REPORT
    from services.device_service import send_frame_and_wait, get_virtual_device

    qframe = pack_status_query()
    resp = send_frame_and_wait(qframe, expect_cmd=CMD_STATUS_REPORT, timeout=1.0)

    if resp:
        # 硬件有应答，用硬件数据恢复
        from services.protocol import parse_status_report
        hw = parse_status_report(resp["data"])
        with _lock:
            _shot_state["running"] = hw["running"]
            _shot_state["elapsed"] = hw["elapsed"]
            _shot_state["total"] = hw["remaining"] + hw["elapsed"]
            _shot_state["remaining"] = hw["remaining"]
            _shot_state["yali_now"] = hw["yali"]
            _shot_state["yao_left"] = hw["yao"]
            _shot_state["mode"] = row["mode"] or "cont"
            _shot_state["ji_liang"] = row["target_dose"]
            _shot_state["lock_token"] = row["lock_token"]
            _shot_state["started_by"] = "(恢复)"
        _persist_device_state()
        print("[RECOVER] 已从硬件恢复状态")

        if ws_pool and hw["running"]:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
            asyncio.run_coroutine_threadsafe(
                ws_pool.blast({"type": "progress", "data": get_shot_state()}),
                loop
            )
    else:
        # 硬件无响应，标记异常终止
        print("[RECOVER] 硬件无响应，上次注射标记为异常终止")
        _clear_device_state()
        db.execute("""
            INSERT INTO alarms (injection_id, alarm_level, msg, yali_val, yao_val)
            VALUES (NULL, 'jiting', '系统重启后硬件无响应，上次注射异常终止', 0, 0)
        """)
        db.commit()
        if ws_pool:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
            asyncio.run_coroutine_threadsafe(
                ws_pool.blast({
                    "type": "notification",
                    "data": {"level": "error", "msg": "系统重启检测到未完成注射，硬件无响应，已标记异常"}
                }),
                loop
            )

# ---------- 曲线相关 ----------

def _build_curve(points_raw):
    pts = sorted(points_raw, key=lambda x: x.get("t", 0))
    result = []
    for i in range(len(pts) - 1):
        result.append((pts[i]["t"], pts[i + 1]["t"], pts[i]["rate"]))
    return result

def _get_curve_rate(elapsed, segments):
    for seg in segments:
        if seg[0] <= elapsed < seg[1]:
            return seg[2]
    if segments and elapsed >= segments[-1][1]:
        return segments[-1][2]
    return 5.0

# ---------- 模拟循环 ----------

def _sim_loop(ws_pool):
    from config import SIM_INTERVAL
    import asyncio

    # 拿到 event loop 引用（只拿一次）
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    last_alarm_lv = None
    last_persist = 0
    persist_interval = 0.2  # 200ms 批量写一次

    while True:
        time.sleep(SIM_INTERVAL)
        with _lock:
            if not _shot_state["running"] or _shot_state["jiting"]:
                last_alarm_lv = None
                continue

            if _shot_state["mode"] == "jianxie" and _shot_state["jian_ge_left"] > 0:
                _shot_state["jian_ge_left"] -= SIM_INTERVAL
                if _shot_state["jian_ge_left"] <= 0:
                    _shot_state["jian_ge_left"] = 0
                st = dict(_shot_state)
                asyncio.run_coroutine_threadsafe(
                    ws_pool.blast({"type": "progress", "data": st}), loop)
                continue

            _shot_state["elapsed"] += SIM_INTERVAL
            _shot_state["remaining"] = max(0, _shot_state["total"] - _shot_state["elapsed"])

            if _shot_state["mode"] == "custom" and _shot_state["curve_points"]:
                _shot_state["su_lv"] = _get_curve_rate(_shot_state["elapsed"], _shot_state["curve_points"])

            base_walk = random.uniform(-1.5, 2.5)
            wave = math.sin(_shot_state["elapsed"] * 0.1) * 1.5
            _shot_state["yali_now"] += base_walk + wave
            _shot_state["yali_now"] = max(0, _shot_state["yali_now"])

            real_decay = (_shot_state["su_lv"] / 3600.0) * SIM_INTERVAL
            _shot_state["yao_left"] = max(0, _shot_state["yao_left"] - real_decay)

            alarm_hit = check_alarms(_shot_state["yali_now"], _shot_state["yao_left"])

            if alarm_hit:
                cur_lv = alarm_hit["level"]
                if cur_lv == last_alarm_lv:
                    alarm_hit["_dup"] = True
                else:
                    last_alarm_lv = cur_lv
            else:
                last_alarm_lv = None

            st = dict(_shot_state)
            st["alarm"] = alarm_hit

            if alarm_hit and alarm_hit["do_jiting"] and not alarm_hit.get("_dup"):
                _shot_state["jiting"] = True
                _shot_state["running"] = False
                _log_alarm_db(alarm_hit)
                _finish_inj_db("jiting")
                _clear_device_state()

            # 广播进度
            asyncio.run_coroutine_threadsafe(
                ws_pool.blast({"type": "progress", "data": st}), loop)

            # 报警广播（不用新线程 + sleep 了）
            if alarm_hit and not alarm_hit.get("_dup"):
                asyncio.run_coroutine_threadsafe(
                    ws_pool.blast({"type": "alarm", "data": alarm_hit}), loop)

            # 注射完成
            if _shot_state["remaining"] <= 0 and _shot_state["total"] > 0:
                _shot_state["running"] = False
                _finish_inj_db("done")
                _clear_device_state()
                asyncio.run_coroutine_threadsafe(
                    ws_pool.blast({"type": "shot_done", "data": dict(_shot_state)}), loop)
                asyncio.run_coroutine_threadsafe(
                    ws_pool.blast({
                        "type": "notification",
                        "data": {"level": "success", "msg": f"注射完成！剂量: {_shot_state['ji_liang']}mL"}
                    }), loop)
                break

            # 间歇模式
            if _shot_state["mode"] == "jianxie" and _shot_state["jian_ge"] > 0:
                if _shot_state["elapsed"] % (_shot_state["jian_ge"] + 10) < SIM_INTERVAL and _shot_state["elapsed"] > 5:
                    _shot_state["jian_ge_left"] = _shot_state["jian_ge"]

            # 每200ms持久化一次
            last_persist += SIM_INTERVAL
            if last_persist >= persist_interval:
                last_persist = 0
                _persist_device_state()

# ---------- 启动/停止 ----------

def start_injection(params: dict, uname: str, ws_pool):
    global _bg_thread, _curve_idx
    lock_tok = str(uuid.uuid4())

    with _lock:
        if _shot_state["running"]:
            return False, "已经有注射在跑了"

        # 原子锁：通过 device_state 表确保唯一
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            UPDATE device_state SET lock_token=?, is_running=1,
                start_time=datetime('now','localtime'), updated_at=datetime('now','localtime')
            WHERE id=1 AND is_running=0
        """, (lock_tok,))
        if cur.rowcount == 0:
            return False, "注射锁被占用（其他终端可能在操作）"

        mode = params.get("mode", "cont")
        su_lv = float(params.get("su_lv", 5))
        ji_liang = float(params.get("ji_liang", 10))
        total_t = float(params.get("total_time", 60))
        jian_ge = float(params.get("jian_ge", 0))
        curve_segs = []
        raw_pts = params.get("curve_points", [])
        if mode == "custom" and raw_pts:
            curve_segs = _build_curve(raw_pts)

        _curve_idx = 0
        _shot_state["running"] = True
        _shot_state["mode"] = mode
        _shot_state["su_lv"] = su_lv
        _shot_state["ji_liang"] = ji_liang
        _shot_state["total"] = total_t
        _shot_state["elapsed"] = 0
        _shot_state["remaining"] = total_t
        _shot_state["yali_now"] = 50.0
        _shot_state["yao_left"] = ji_liang
        _shot_state["started_by"] = uname
        _shot_state["jiting"] = False
        _shot_state["paused"] = False
        _shot_state["jian_ge"] = jian_ge
        _shot_state["jian_ge_left"] = 0
        _shot_state["curve_points"] = curve_segs
        _shot_state["lock_token"] = lock_tok

        # DB 记录
        urow = db.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
        uid = urow["id"] if urow else 1
        cur.execute("""
            INSERT INTO injections (user_id, shot_mode, su_lv, ji_liang, total_time, jian_ge, status, started_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?)
        """, (uid, mode, su_lv, ji_liang, total_t, jian_ge, datetime.now().isoformat(), params.get("notes", "")))
        db.commit()
        _shot_state["record_id"] = cur.lastrowid

        _persist_device_state()

    _bg_thread = threading.Thread(target=_sim_loop, args=(ws_pool,), daemon=True)
    _bg_thread.start()
    return True, f"注射已启动, 模式: {mode}"

def stop_injection(uname: str, lock_token: str = None, force: bool = False):
    """停止注射，管理员可强制（force=True 跳过 lock_token 检查）"""
    with _lock:
        if not _shot_state["running"]:
            return False, "没在跑"
        if not force and lock_token and _shot_state.get("lock_token") != lock_token:
            return False, "不是你的锁，不能停"
        _shot_state["running"] = False
        _shot_state["elapsed"] = _shot_state["total"] - _shot_state["remaining"]
        _finish_inj_db("stopped")
        _clear_device_state()
        db = get_db()
        from auth import sign_log_entry
        sig = sign_log_entry(0, "ws", f"停止注射 #{_shot_state.get('record_id')}")
        db.execute("INSERT INTO op_logs (user_id, username, action, ip_addr, signature) VALUES (?,?,?,?,?)",
                   (0, uname, f"停止注射 #{_shot_state.get('record_id')}", "ws", sig))
        db.commit()
        return True, "已停止"

def _finish_inj_db(status: str):
    rid = _shot_state.get("record_id")
    if not rid:
        return
    db = get_db()
    real_dose = _shot_state.get("ji_liang", 0) - _shot_state.get("yao_left", 0)
    db.execute("""
        UPDATE injections SET status=?, ended_at=?, real_dose=? WHERE id=?
    """, (status, datetime.now().isoformat(), max(0, real_dose), rid))
    db.commit()

def _log_alarm_db(alarm_info: dict):
    db = get_db()
    db.execute("""
        INSERT INTO alarms (injection_id, alarm_level, msg, yali_val, yao_val)
        VALUES (?, ?, ?, ?, ?)
    """, (
        _shot_state.get("record_id"),
        alarm_info.get("level", "warn1"),
        alarm_info.get("msg", ""),
        alarm_info.get("yali", 0),
        alarm_info.get("yao", 0),
    ))
    db.commit()

# ---------- 历史/推荐 ----------

def get_shot_history(page=1, page_size=20, start_d="", end_d="", mode="", min_dose=None, max_dose=None):
    db = get_db()
    sql = "SELECT i.*, u.username FROM injections i LEFT JOIN users u ON i.user_id = u.id WHERE 1=1"
    params = []
    if start_d:
        sql += " AND i.started_at >= ?"
        params.append(start_d)
    if end_d:
        sql += " AND i.started_at <= ?"
        params.append(end_d + " 23:59:59")
    if mode:
        sql += " AND i.shot_mode = ?"
        params.append(mode)
    if min_dose is not None:
        sql += " AND i.ji_liang >= ?"
        params.append(min_dose)
    if max_dose is not None:
        sql += " AND i.ji_liang <= ?"
        params.append(max_dose)
    count_sql = sql.replace("SELECT i.*, u.username", "SELECT COUNT(*) as c")
    total = db.execute(count_sql, params).fetchone()["c"]
    sql += " ORDER BY i.started_at DESC LIMIT ? OFFSET ?"
    params.extend([page_size, (page - 1) * page_size])
    rows = db.execute(sql, params).fetchall()
    return {"list": [dict(r) for r in rows], "total": total, "page": page}

def get_yao_recommend(user_id: int = None):
    db = get_db()
    rows = db.execute("""
        SELECT ji_liang, shot_mode FROM injections WHERE status != 'running'
        ORDER BY started_at DESC LIMIT 5
    """).fetchall()
    if not rows:
        return {"recommend": 10.0, "avg_su_lv": 5.0, "mode_hint": "cont"}
    vals = [r["ji_liang"] for r in rows]
    n = len(vals)
    if n == 1:
        return {"recommend": vals[0], "avg_su_lv": 5.0, "mode_hint": rows[0]["shot_mode"]}
    total_w, total_v = 0, 0
    for i, v in enumerate(vals):
        w = i + 1
        total_w += w
        total_v += v * w
    modes = [r["shot_mode"] for r in rows]
    mode_hint = max(set(modes), key=modes.count)
    return {
        "recommend": round(total_v / total_w, 2),
        "avg_su_lv": round((total_v / total_w) / 60 * 3600, 1),
        "mode_hint": mode_hint
    }

def get_running_shot():
    db = get_db()
    row = db.execute("SELECT * FROM injections WHERE status='running' ORDER BY started_at DESC LIMIT 1").fetchone()
    if row:
        d = dict(row)
        d["state"] = get_shot_state()
        return d
    return None

def count_today_shots():
    db = get_db()
    row = db.execute("SELECT COUNT(*) as c FROM injections WHERE DATE(started_at)=DATE('now')").fetchone()
    return row["c"] if row else 0

def get_latest_alarms(limit=5):
    db = get_db()
    rows = db.execute("SELECT * FROM alarms ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
