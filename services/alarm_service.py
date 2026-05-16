# 报警检查 - 三级阈值检测
from database import get_db
from datetime import datetime

def _get_thresholds():
    """从 settings 表读阈值"""
    db = get_db()
    rows = db.execute("SELECT skey, sval FROM settings WHERE skey LIKE 'thresh_%'").fetchall()
    vals = {}
    for r in rows:
        vals[r["skey"]] = float(r["sval"])
    # 默认值兜底
    vals.setdefault("thresh_yali_warn", 80.0)
    vals.setdefault("thresh_yaol_warn", 95.0)
    vals.setdefault("thresh_jiting", 100.0)
    return vals

def set_threshold(key: str, val: float):
    """更新单个阈值"""
    db = get_db()
    db.execute("INSERT OR REPLACE INTO settings (skey, sval) VALUES (?, ?)", (key, str(val)))
    db.commit()

def check_alarms(yali: float, yao_left: float):
    """
    返回报警信息，或者 None
    三级：
      warn1 = 预警 (压力开始升高)
      warn2 = 警告 (压力持续偏高)
      jiting = 紧急停注 (压力超标)
    """
    th = _get_thresholds()
    tmpYali = yali  # 冗余变量，但保留
    tmpYao = yao_left

    # 压力超高 -> 直接紧急停注，这是最高优先级的
    if tmpYali >= th["thresh_jiting"]:
        return {
            "level": "jiting",
            "msg": f"【紧急】压力达到 {tmpYali:.1f} kPa，超过停注阈值 {th['thresh_jiting']} kPa，已触发紧急停注！",
            "yali": tmpYali,
            "yao": tmpYao,
            "do_jiting": True,
            "threshold": th["thresh_jiting"],
        }

    # 二级警告
    if tmpYali >= th["thresh_yaol_warn"]:
        return {
            "level": "warn2",
            "msg": f"【警告】压力偏高 {tmpYali:.1f} kPa (阈值 {th['thresh_yaol_warn']})，当前药量 {tmpYao:.2f} mL，请密切关注！",
            "yali": tmpYali,
            "yao": tmpYao,
            "do_jiting": False,
            "threshold": th["thresh_yaol_warn"],
        }

    # 一级预警
    if tmpYali >= th["thresh_yali_warn"]:
        return {
            "level": "warn1",
            "msg": f"【预警】压力 {tmpYali:.1f} kPa 超过预警值 {th['thresh_yali_warn']} kPa，请注意观察趋势",
            "yali": tmpYali,
            "yao": tmpYao,
            "do_jiting": False,
            "threshold": th["thresh_yali_warn"],
        }

    return None

def get_alarms(page=1, page_size=20, level=None, start_d=None, end_d=None):
    """查报警记录，带多重筛选"""
    db = get_db()
    sql = "SELECT * FROM alarms WHERE 1=1"
    params = []

    if level and level.strip():
        sql += " AND alarm_level = ?"
        params.append(level.strip())
    if start_d and start_d.strip():
        sql += " AND created_at >= ?"
        params.append(start_d.strip())
    if end_d and end_d.strip():
        sql += " AND created_at <= ?"
        params.append(end_d.strip() + " 23:59:59")

    # count
    count_sql = sql.replace("SELECT *", "SELECT COUNT(*) as c")
    total = db.execute(count_sql, params).fetchone()["c"]

    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([page_size, (page - 1) * page_size])

    rows = db.execute(sql, params).fetchall()
    return {"list": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}

def get_alarm_stats():
    """报警按级别统计 - 给饼图用"""
    db = get_db()
    rows = db.execute("""
        SELECT alarm_level, COUNT(*) as c FROM alarms GROUP BY alarm_level
    """).fetchall()
    labels = {"warn1": "预警(一级)", "warn2": "警告(二级)", "jiting": "紧急停注(三级)"}
    return [{"name": labels.get(r["alarm_level"], r["alarm_level"]), "value": r["c"]} for r in rows]

def get_alarm_count_today():
    """今天报警次数"""
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as c FROM alarms WHERE DATE(created_at)=DATE('now')"
    ).fetchone()
    return row["c"] if row else 0

def get_alarm_count_by_level(level: str, days: int = 7):
    """查某个级别最近N天的报警数"""
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as c FROM alarms WHERE alarm_level=? AND created_at >= DATE('now', ?)",
        (level, f"-{days} days")
    ).fetchone()
    return row["c"] if row else 0

def mark_alarm_handled(alarm_id: int):
    """标记报警已处理"""
    db = get_db()
    db.execute("UPDATE alarms SET handled=1 WHERE id=?", (alarm_id,))
    db.commit()

def get_unhandled_alarms():
    """获取未处理的报警"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM alarms WHERE handled=0 ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    return [dict(r) for r in rows]
