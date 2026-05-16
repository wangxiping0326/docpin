# 注射核心业务逻辑 - 有点乱，但能用
import threading
import time
import random
import math
from datetime import datetime
from database import get_db
from services.alarm_service import check_alarms
from services.device_service import get_device_status, is_sim_mode

# 当前注射状态 - 全局的，简单粗暴
_shot_state = {
    "running": False,
    "mode": "",
    "su_lv": 0,
    "ji_liang": 0,
    "total": 0,
    "elapsed": 0,
    "remaining": 0,
    "yali_now": 50.0,
    "yao_left": 10.0,
    "started_by": "",  # 谁启动的
    "device_id": None,
    "record_id": None,
    "jiting": False,  # 是否被紧急中断
    "paused": False,
    "curve_points": [],  # 自定义曲线用的
    "jian_ge": 0,        # 间隔时间
    "jian_ge_left": 0,   # 间隔剩余
}

_lock = threading.Lock()
_bg_thread = None
_curve_idx = 0  # 自定义曲线当前段

def get_shot_state():
    with _lock:
        return dict(_shot_state)

# ---------- 自定义曲线相关 ----------

def _build_curve(points_raw):
    """把前端传来的曲线点转成内部格式
    points_raw: [{"t": 0, "rate": 5}, {"t": 30, "rate": 8}, ...]
    返回: [(t_start, t_end, rate), ...]
    """
    pts = sorted(points_raw, key=lambda x: x.get("t", 0))
    result = []
    for i in range(len(pts) - 1):
        t0 = pts[i]["t"]
        t1 = pts[i + 1]["t"]
        r = pts[i]["rate"]
        result.append((t0, t1, r))
    return result

def _get_curve_rate(elapsed, segments):
    """根据已用时间查曲线速率"""
    for seg in segments:
        if seg[0] <= elapsed < seg[1]:
            return seg[2]
    if segments and elapsed >= segments[-1][1]:
        return segments[-1][2]
    return 5.0  # fallback

# ---------- 模拟后台循环 ----------

def _sim_loop(ws_pool):
    """后台线程 - 模拟注射过程 + 压力/药量变化"""
    from config import SIM_PRESSURE_BASE, SIM_YAOLIANG_RATE, SIM_INTERVAL
    import asyncio

    # 搞个临时变量防止重复报警
    last_alarm_lv = None

    while True:
        time.sleep(SIM_INTERVAL)
        with _lock:
            if not _shot_state["running"] or _shot_state["jiting"]:
                last_alarm_lv = None
                continue

            # 间歇模式处理：如果在间隔期就先等着
            if _shot_state["mode"] == "jianxie" and _shot_state["jian_ge_left"] > 0:
                _shot_state["jian_ge_left"] -= SIM_INTERVAL
                if _shot_state["jian_ge_left"] <= 0:
                    _shot_state["jian_ge_left"] = 0
                st = dict(_shot_state)
                # 间隔中也推状态
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                asyncio.run_coroutine_threadsafe(
                    ws_pool.blast({"type": "progress", "data": st}),
                    loop
                )
                continue

            # 增加已用时间
            _shot_state["elapsed"] += SIM_INTERVAL
            _shot_state["remaining"] = max(0, _shot_state["total"] - _shot_state["elapsed"])

            # 自定义曲线模式 - 根据曲线调整当前速率
            if _shot_state["mode"] == "custom" and _shot_state["curve_points"]:
                cur_rate = _get_curve_rate(_shot_state["elapsed"], _shot_state["curve_points"])
                _shot_state["su_lv"] = cur_rate

            # 模拟压力变化 - 随机漫步 + 周期性波动
            base_walk = random.uniform(-1.5, 2.5)
            wave = math.sin(_shot_state["elapsed"] * 0.1) * 1.5  # 加个正弦波动
            delta_p = base_walk + wave
            _shot_state["yali_now"] += delta_p
            if _shot_state["yali_now"] < 0:
                _shot_state["yali_now"] = 0

            # 药量递减（与实际速率挂钩）
            real_decay = (_shot_state["su_lv"] / 3600.0) * SIM_INTERVAL
            _shot_state["yao_left"] -= real_decay
            if _shot_state["yao_left"] < 0:
                _shot_state["yao_left"] = 0

            # 检查是否需要报警
            alarm_hit = check_alarms(_shot_state["yali_now"], _shot_state["yao_left"])

            # 避免重复报警刷屏
            if alarm_hit:
                cur_lv = alarm_hit["level"]
                if cur_lv == last_alarm_lv:
                    alarm_hit["_dup"] = True  # 标记重复，只推进度不推 alarm 事件
                else:
                    last_alarm_lv = cur_lv
            else:
                last_alarm_lv = None

            st = dict(_shot_state)
            st["alarm"] = alarm_hit

            # push 进度给所有客户端
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if alarm_hit and alarm_hit["do_jiting"] and not alarm_hit.get("_dup"):
                _shot_state["jiting"] = True
                _shot_state["running"] = False
                _log_alarm_db(alarm_hit)
                _finish_inj_db("jiting")

            # 广播进度
            asyncio.run_coroutine_threadsafe(
                ws_pool.blast({"type": "progress", "data": st}),
                loop
            )

            if alarm_hit and not alarm_hit.get("_dup"):
                # setTimeout 风格的延时广播，避免太密集
                def delayed_broadcast(alarm_data):
                    time.sleep(0.3)
                    try:
                        loop2 = asyncio.get_event_loop()
                    except RuntimeError:
                        loop2 = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop2)
                    asyncio.run_coroutine_threadsafe(
                        ws_pool.blast({"type": "alarm", "data": alarm_data}),
                        loop2
                    )
                t = threading.Thread(target=delayed_broadcast, args=(alarm_hit,), daemon=True)
                t.start()

            # 注射完成
            if _shot_state["remaining"] <= 0 and _shot_state["total"] > 0:
                _shot_state["running"] = False
                _finish_inj_db("done")
                asyncio.run_coroutine_threadsafe(
                    ws_pool.blast({"type": "shot_done", "data": dict(_shot_state)}),
                    loop
                )
                # 触发完成通知
                asyncio.run_coroutine_threadsafe(
                    ws_pool.blast({
                        "type": "notification",
                        "data": {
                            "level": "success",
                            "msg": f"注射完成！模式: {_shot_state['mode']}, 剂量: {_shot_state['ji_liang']}mL"
                        }
                    }),
                    loop
                )
                break

            # 间歇模式：到了一段时间就切到间隔
            if _shot_state["mode"] == "jianxie" and _shot_state["jian_ge"] > 0:
                cycle_time = _shot_state["total"] / (1 + _shot_state["jian_ge"]) if _shot_state["jian_ge"] > 0 else _shot_state["total"]
                # 简化：每隔一段时间就歇
                if _shot_state["elapsed"] % (_shot_state["jian_ge"] + 10) < SIM_INTERVAL and _shot_state["elapsed"] > 5:
                    _shot_state["jian_ge_left"] = _shot_state["jian_ge"]

# ---------- 启动/停止 ----------

def start_injection(params: dict, uname: str, ws_pool):
    """开始打药"""
    global _bg_thread, _curve_idx
    with _lock:
        if _shot_state["running"]:
            return False, "已经有注射在跑了，先停了再说"

        mode = params.get("mode", "cont")
        su_lv = float(params.get("su_lv", 5))
        ji_liang = float(params.get("ji_liang", 10))
        total_t = float(params.get("total_time", 60))
        jian_ge = float(params.get("jian_ge", 0))

        # 自定义曲线 - 解析曲线点
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
        _shot_state["yao_left"] = ji_liang  # 初始药量=剂量
        _shot_state["started_by"] = uname
        _shot_state["jiting"] = False
        _shot_state["paused"] = False
        _shot_state["jian_ge"] = jian_ge
        _shot_state["jian_ge_left"] = 0
        _shot_state["curve_points"] = curve_segs

        # 写一条 DB 记录 - 顺便记下用户ID
        db = get_db()
        cur = db.cursor()
        # 先通过用户名找 uid
        urow = db.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
        uid = urow["id"] if urow else 1

        cur.execute("""
            INSERT INTO injections (user_id, shot_mode, su_lv, ji_liang, total_time, jian_ge, status, started_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?)
        """, (uid, mode, su_lv, ji_liang, total_t, jian_ge, datetime.now().isoformat(), params.get("notes", "")))
        db.commit()
        _shot_state["record_id"] = cur.lastrowid

    # 启动模拟线程
    _bg_thread = threading.Thread(target=_sim_loop, args=(ws_pool,), daemon=True)
    _bg_thread.start()

    return True, f"注射已启动, 模式: {mode}"

def stop_injection(uname: str):
    """停止注射 - 谁都可以停，但记录是谁停的"""
    with _lock:
        if not _shot_state["running"]:
            return False, "没在跑，停啥"
        _shot_state["running"] = False
        _shot_state["elapsed"] = _shot_state["total"] - _shot_state["remaining"]
        _finish_inj_db("stopped")
        # 记录操作
        db = get_db()
        db.execute("INSERT INTO op_logs (user_id, username, action, ip_addr) VALUES (?,?,?,?)",
                   (0, uname, f"停止注射 #{_shot_state.get('record_id')}", "ws"))
        db.commit()
        return True, "已停止"

def _finish_inj_db(status: str):
    """更新 DB 里的注射记录状态"""
    rid = _shot_state.get("record_id")
    if not rid:
        return
    db = get_db()
    real_dose = _shot_state.get("ji_liang", 0) - _shot_state.get("yao_left", 0)
    db.execute("""
        UPDATE injections SET status=?, ended_at=?, real_dose=?
        WHERE id=?
    """, (status, datetime.now().isoformat(), max(0, real_dose), rid))
    db.commit()

def _log_alarm_db(alarm_info: dict):
    """把报警写进 alarms 表"""
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

# ---------- 历史记录辅助 ----------

def get_shot_history(page=1, page_size=20, start_d="", end_d="", mode="", min_dose=None, max_dose=None):
    """查注射历史，多条件筛选"""
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

# ---------- 剂量推荐 ----------

def get_yao_recommend(user_id: int = None):
    """剂量推荐 - 最近5次加权平均 + 模式适配"""
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

    total_w = 0
    total_v = 0
    for i, v in enumerate(vals):
        w = i + 1
        total_w += w
        total_v += v * w
    # 最常见的模式
    modes = [r["shot_mode"] for r in rows]
    mode_hint = max(set(modes), key=modes.count)

    return {
        "recommend": round(total_v / total_w, 2),
        "avg_su_lv": round((total_v / total_w) / 60 * 3600, 1),  # 估算速率
        "mode_hint": mode_hint
    }

# ---------- 几个冗余的查询方法（为了多端复用） ----------

def get_running_shot():
    """查询当前是否有正在跑的注射"""
    db = get_db()
    row = db.execute("SELECT * FROM injections WHERE status='running' ORDER BY started_at DESC LIMIT 1").fetchone()
    if row:
        d = dict(row)
        d["state"] = get_shot_state()
        return d
    return None

def count_today_shots():
    """今天打了几次"""
    db = get_db()
    row = db.execute("SELECT COUNT(*) as c FROM injections WHERE DATE(started_at)=DATE('now')").fetchone()
    return row["c"] if row else 0

def get_latest_alarms(limit=5):
    """最近几条报警"""
    db = get_db()
    rows = db.execute("SELECT * FROM alarms ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
