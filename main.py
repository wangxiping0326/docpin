"""
高精度智能电子注射器管控系统
启动方式: pip install -r requirements.txt && python main.py
然后浏览器打开 http://localhost:8000
"""
import os
import sys
import json
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
import uvicorn

from config import FRONTEND_DIR
from database import init_db
from services.device_service import init_device
from ws_manager import ws_pool
from auth import parse_token

# 创建 app
app = FastAPI(title="高精度智能电子注射器管控系统", version="1.0.0", docs_url="/api/docs")

# CORS - 局域网多终端嘛，放通
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 简单的请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    # 只打 API 请求的日志
    if request.url.path.startswith("/api"):
        print(f"[REQ] {request.method} {request.url.path} -> {response.status_code} ({elapsed:.2f}s)")
    return response

# 全局异常处理
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": f"参数校验失败: {exc.errors()}"}
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    # 对于前端路由，返回 index.html
    if not request.url.path.startswith("/api") and not request.url.path.startswith("/ws"):
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"detail": "请求的资源不存在"})

# 注册路由
from routes.auth_routes import router as auth_r
from routes.injection_routes import router as shot_r
from routes.device_routes import router as dev_r
from routes.alarm_routes import router as alarm_r
from routes.stats_routes import router as stats_r

app.include_router(auth_r)
app.include_router(shot_r)
app.include_router(dev_r)
app.include_router(alarm_r)
app.include_router(stats_r)

# WebSocket 端点
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()

    # 第一帧拿 token 做认证
    try:
        first_msg = await ws.receive_text()
        data = json.loads(first_msg)
        tok = data.get("token", "")
        payload = parse_token(tok)
        if not payload:
            await ws.send_text(json.dumps({"type": "err", "msg": "token 无效或过期"}))
            await ws.close()
            return
        await ws_pool.add_one(ws, payload["uid"], payload["uname"])
        await ws.send_text(json.dumps({
            "type": "hello",
            "data": {
                "msg": f"已连接, {payload['uname']}",
                "role": payload["role"],
                "conn_count": await ws_pool.get_count(),
            }
        }))

        # 把当前注射状态推过去
        from services.injection_service import get_shot_state
        st = get_shot_state()
        await ws.send_text(json.dumps({"type": "progress", "data": st}))

    except WebSocketDisconnect:
        return
    except Exception as e:
        print(f"[WS] 认证失败: {e}")
        try:
            await ws.send_text(json.dumps({"type": "err", "msg": f"认证失败: {str(e)}"}))
            await ws.close()
        except Exception:
            pass
        return

    # 一直挂着收消息
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                msgType = msg.get("type", "")
                if msgType == "ping":
                    await ws.send_text(json.dumps({
                        "type": "pong",
                        "server_time": time.time(),
                        "conn_count": await ws_pool.get_count(),
                    }))
                elif msgType == "get_status":
                    from services.injection_service import get_shot_state
                    st = get_shot_state()
                    await ws.send_text(json.dumps({"type": "progress", "data": st}))
                elif msgType == "get_devices":
                    from services.device_service import get_device_status
                    ds = get_device_status()
                    await ws.send_text(json.dumps({"type": "devices", "data": ds}))
                # 其他消息类型就忽略
            except json.JSONDecodeError:
                pass
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"[WS] 消息处理异常: {e}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] 连接异常退出: {e}")
    finally:
        await ws_pool.kick_one(ws)

# 健康检查（必须在 SPA catch-all 之前注册）
@app.get("/api/health")
async def health():
    from services.device_service import get_device_status
    from datetime import datetime
    return {
        "status": "ok",
        "time": datetime.now().isoformat(),
        "ws_connections": await ws_pool.get_count(),
        "device_mode": get_device_status().get("sim_mode", True),
    }

# 挂静态文件 - 前端 build 产物
if os.path.exists(FRONTEND_DIR):
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """SPA fallback - 非 API 路径都返回 index.html"""
        if full_path.startswith("api/") or full_path.startswith("ws"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # SPA fallback
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"msg": "前端还没 build，去 frontend 目录 npm run build"}
    print(f"[APP] 前端静态文件已挂载: {FRONTEND_DIR}")
else:
    @app.get("/")
    async def root_no_fe():
        return {
            "msg": "后端跑起来了！",
            "hint": "前端还没build，请 cd frontend && npm install && npm run build",
            "api_docs": "/api/docs",
        }

    print(f"[APP] 警告: 没找到前端 build 目录 {FRONTEND_DIR}")

# 启动时初始化
@app.on_event("startup")
async def on_startup():
    print("=" * 50)
    print("  高精度智能电子注射器管控系统 启动中...")
    print("=" * 50)
    init_db()
    init_device()
    print(f"[APP] 系统就绪，访问 http://localhost:8000")
    print(f"[APP] API 文档: http://localhost:8000/api/docs")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
