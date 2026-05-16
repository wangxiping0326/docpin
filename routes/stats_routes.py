# 统计 + 导出路由
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from routes.auth_routes import _get_user_from_req
from database import get_db
from services.alarm_service import get_alarm_stats
from services.injection_service import count_today_shots, get_latest_alarms, get_running_shot
import io
import csv
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/stats", tags=["stats"])

@router.get("/dose")
async def dose_stats(req: Request, period: str = "day"):
    """日/周/月剂量趋势"""
    _get_user_from_req(req)
    db = get_db()

    if period == "day":
        sql = """
            SELECT DATE(started_at) as dt, SUM(ji_liang) as total_dose, COUNT(*) as cnt
            FROM injections WHERE started_at >= DATE('now', '-30 days')
            GROUP BY DATE(started_at) ORDER BY dt
        """
    elif period == "week":
        sql = """
            SELECT strftime('%Y-W%W', started_at) as dt, SUM(ji_liang) as total_dose, COUNT(*) as cnt
            FROM injections WHERE started_at >= DATE('now', '-90 days')
            GROUP BY dt ORDER BY dt
        """
    else:  # month
        sql = """
            SELECT strftime('%Y-%m', started_at) as dt, SUM(ji_liang) as total_dose, COUNT(*) as cnt
            FROM injections WHERE started_at >= DATE('now', '-12 months')
            GROUP BY dt ORDER BY dt
        """

    rows = db.execute(sql).fetchall()
    return [dict(r) for r in rows]

@router.get("/overview")
async def overview_stats(req: Request):
    """仪表盘总览数据 - 一次返回多个指标"""
    _get_user_from_req(req)
    db = get_db()

    # 今天注射次数
    today_cnt = count_today_shots()

    # 总注射次数
    total_cnt = db.execute("SELECT COUNT(*) as c FROM injections").fetchone()["c"]

    # 总报警数
    alarm_cnt = db.execute("SELECT COUNT(*) as c FROM alarms").fetchone()["c"]

    # 最近 7 天注射趋势
    week_rows = db.execute("""
        SELECT DATE(started_at) as dt, COUNT(*) as cnt, SUM(ji_liang) as total_dose
        FROM injections WHERE started_at >= DATE('now', '-7 days')
        GROUP BY DATE(started_at) ORDER BY dt
    """).fetchall()

    # 各模式使用次数
    mode_rows = db.execute("""
        SELECT shot_mode, COUNT(*) as cnt FROM injections GROUP BY shot_mode
    """).fetchall()

    # 最近报警
    latest_alarms = get_latest_alarms(5)

    # 设备数量
    dev_cnt = db.execute("SELECT COUNT(*) as c FROM devices").fetchone()["c"]

    return {
        "today_shots": today_cnt,
        "total_shots": total_cnt,
        "total_alarms": alarm_cnt,
        "device_count": dev_cnt,
        "week_trend": [dict(r) for r in week_rows],
        "mode_usage": [dict(r) for r in mode_rows],
        "latest_alarms": latest_alarms,
    }

@router.get("/mode_stats")
async def mode_statistics(req: Request):
    """按模式统计 - 平均剂量、次数、成功率"""
    _get_user_from_req(req)
    db = get_db()
    rows = db.execute("""
        SELECT shot_mode,
               COUNT(*) as cnt,
               AVG(ji_liang) as avg_dose,
               AVG(total_time) as avg_time,
               SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done_cnt,
               SUM(CASE WHEN status='jiting' THEN 1 ELSE 0 END) as jiting_cnt
        FROM injections
        GROUP BY shot_mode
    """).fetchall()
    mode_names = {"cont": "持续输注", "jianxie": "间歇输注", "tui": "按需推注", "custom": "自定义曲线"}
    result = []
    for r in rows:
        d = dict(r)
        d["mode_name"] = mode_names.get(d["shot_mode"], d["shot_mode"])
        result.append(d)
    return result

@router.get("/export")
async def export_excel(req: Request, start_d: str = "", end_d: str = ""):
    """导出注射记录到 CSV（Excel 兼容）"""
    _get_user_from_req(req)
    db = get_db()

    sql = """
        SELECT i.id, u.username, i.shot_mode, i.su_lv, i.ji_liang,
               i.total_time, i.real_dose, i.status, i.started_at, i.ended_at, i.notes
        FROM injections i LEFT JOIN users u ON i.user_id = u.id WHERE 1=1
    """
    params = []
    if start_d:
        sql += " AND i.started_at >= ?"
        params.append(start_d)
    if end_d:
        sql += " AND i.started_at <= ?"
        params.append(end_d + " 23:59:59")
    sql += " ORDER BY i.started_at DESC"

    rows = db.execute(sql, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "操作员", "模式", "速率(mL/h)", "剂量(mL)", "时长(s)", "实际药量(mL)", "状态", "开始时间", "结束时间", "备注"])
    mode_names = {"cont": "持续输注", "jianxie": "间歇输注", "tui": "按需推注", "custom": "自定义曲线"}
    status_names = {"done": "完成", "stopped": "手动停止", "jiting": "紧急停注", "running": "运行中"}
    for r in rows:
        writer.writerow([
            r["id"],
            r["username"],
            mode_names.get(r["shot_mode"], r["shot_mode"]),
            r["su_lv"],
            r["ji_liang"],
            r["total_time"],
            r["real_dose"] or "",
            status_names.get(r["status"], r["status"]),
            r["started_at"],
            r["ended_at"] or "",
            r["notes"] or "",
        ])

    output.seek(0)
    filename = f"injection_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ---------- 操作日志 ----------

@router.get("/logs")
async def op_logs(req: Request, page: int = 1, page_size: int = 30, username: str = ""):
    _get_user_from_req(req)
    db = get_db()
    sql = "SELECT * FROM op_logs WHERE 1=1"
    params = []
    if username:
        sql += " AND username LIKE ?"
        params.append(f"%{username}%")
    total = db.execute(sql.replace("SELECT *", "SELECT COUNT(*) as c"), params).fetchone()["c"]
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([page_size, (page - 1) * page_size])
    rows = db.execute(sql, params).fetchall()
    return {"list": [dict(r) for r in rows], "total": total}

@router.post("/logs/clean")
async def clean_logs(req: Request):
    """清理旧日志"""
    payload = _get_user_from_req(req)
    if payload["role"] != "admin":
        raise HTTPException(403, "admin only")
    data = await req.json()
    days = int(data.get("days", 90))
    db = get_db()
    db.execute("DELETE FROM op_logs WHERE created_at < DATE('now', ?)", (f"-{days} days",))
    db.commit()
    return {"ok": True, "msg": f"已清理 {days} 天前的日志"}

# ---------- 报警统计 ----------

@router.get("/alarm_trend")
async def alarm_trend(req: Request):
    """报警趋势 - 最近 30 天按天汇总"""
    _get_user_from_req(req)
    db = get_db()
    rows = db.execute("""
        SELECT DATE(created_at) as dt, alarm_level, COUNT(*) as cnt
        FROM alarms WHERE created_at >= DATE('now', '-30 days')
        GROUP BY DATE(created_at), alarm_level
        ORDER BY dt
    """).fetchall()
    # 转成前端好用的格式
    result = {}
    for r in rows:
        dt = r["dt"]
        if dt not in result:
            result[dt] = {"dt": dt, "warn1": 0, "warn2": 0, "jiting": 0}
        result[dt][r["alarm_level"]] = r["cnt"]
    return list(result.values())

@router.get("/daily_summary")
async def daily_summary(req: Request, date: str = ""):
    """某天的摘要 - 注射次数、总剂量、报警数"""
    _get_user_from_req(req)
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    db = get_db()
    shot_cnt = db.execute(
        "SELECT COUNT(*) as c FROM injections WHERE DATE(started_at)=?", (date,)
    ).fetchone()["c"]
    total_dose = db.execute(
        "SELECT COALESCE(SUM(ji_liang), 0) as s FROM injections WHERE DATE(started_at)=?", (date,)
    ).fetchone()["s"]
    alarm_cnt = db.execute(
        "SELECT COUNT(*) as c FROM alarms WHERE DATE(created_at)=?", (date,)
    ).fetchone()["c"]
    return {
        "date": date,
        "shot_count": shot_cnt,
        "total_dose": round(total_dose, 2),
        "alarm_count": alarm_cnt,
    }
