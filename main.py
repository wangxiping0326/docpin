"""
高精度智能电子注射器管控系统
启动: python main.py
"""
import os
import sys
import json
import time

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[APP] .env 文件已加载")
except ImportError:
    print("[APP] python-dotenv 未安装，跳过 .env 加载（pip install python-dotenv 可启用）")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
import uvicorn

from config import FRONTEND_DIR, SHOW_DOCS, JWT_TTL
from database import init_db
from services.device_service import init_device
from ws_manager import ws_pool
from auth import parse_token, make_refresh_token

app = FastAPI(
    title="高精度智能电子注射器管控系统",
    version="2.0.0",
    docs_url="/api/docs" if SHOW_DOCS else None,
    redoc_url=None if not SHOW_DOCS else "/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    if request.url.path.startswith("/api"):
        print(f"[REQ] {request.method} {request.url.path} -> {response.status_code} ({elapsed:.2f}s)")
    return response

@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": f"参数校验失败: {exc.errors()}"})

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

# WebSocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        first_msg = await ws.receive_text()
        data = json.loads(first_msg)
        tok = data.get("token", "")
        payload = parse_token(tok)
        if not payload:
            await ws.send_text(json.dumps({"type": "err", "msg": "token 无效或过期"}))
            await ws.close()
            return
        token_exp = payload.get("exp", 0)
        await ws_pool.add_one(ws, payload["uid"], payload["uname"], token_exp)
        await ws.send_text(json.dumps({
            "type": "hello",
            "data": {
                "msg": f"已连接, {payload['uname']}",
                "role": payload["role"],
                "conn_count": await ws_pool.get_count(),
            }
        }))
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

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                msgType = msg.get("type", "")

                # 检查 token 是否过期
                await ws_pool.check_token_expiry()

                if msgType == "ping":
                    await ws.send_text(json.dumps({
                        "type": "pong", "server_time": time.time(),
                        "conn_count": await ws_pool.get_count(),
                    }))
                elif msgType == "refresh_token":
                    # 客户端发来 refresh_token，更新连接
                    rt = msg.get("refresh_token", "")
                    from auth import parse_token_allow_expired, make_token
                    rp = parse_token_allow_expired(rt)
                    if rp and rp.get("type") == "refresh":
                        new_tok = make_token(rp["uid"], rp["uname"], rp["role"])
                        from auth import parse_token
                        np = parse_token(new_tok)
                        if np:
                            await ws_pool.update_token_exp(ws, np.get("exp", 0))
                            await ws.send_text(json.dumps({
                                "type": "token_refreshed",
                                "token": new_tok,
                                "token_exp": np.get("exp", 0),
                            }))
                elif msgType == "get_status":
                    from services.injection_service import get_shot_state
                    await ws.send_text(json.dumps({"type": "progress", "data": get_shot_state()}))
                elif msgType == "get_devices":
                    from services.device_service import get_device_status
                    await ws.send_text(json.dumps({"type": "devices", "data": get_device_status()}))
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

# 健康检查（SPA catch-all 之前注册）
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

# 挂静态文件
if os.path.exists(FRONTEND_DIR):
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"msg": "前端还没 build，去 frontend 目录 npm run build"}
    print(f"[APP] 前端静态文件已挂载: {FRONTEND_DIR}")
else:
    @app.get("/")
    async def root_no_fe():
        return {"msg": "后端跑起来了！", "hint": "请 cd frontend && npm install && npm run build"}
    print(f"[APP] 警告: 没找到前端 build 目录")

# 启动事件
@app.on_event("startup")
async def on_startup():
    print("=" * 50)
    print("  高精度智能电子注射器管控系统 启动中...")
    print("=" * 50)
    init_db()
    init_device(ws_pool)
    # 状态恢复
    from services.injection_service import recover_state
    recover_state(ws_pool)
    print(f"[APP] 系统就绪，访问 http://localhost:8000")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
