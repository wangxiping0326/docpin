# WebSocket 连接池 - 管理所有连着的终端
from fastapi import WebSocket
import json
import asyncio

class WSManager:
    """管所有 ws 连接 + 广播"""
    def __init__(self):
        self.pool = []  # [(ws, uid, uname), ...]
        self._lock = asyncio.Lock()

    async def add_one(self, ws: WebSocket, uid: int, uname: str):
        async with self._lock:
            self.pool.append((ws, uid, uname))
            print(f"[WS] {uname} 连上了, 当前连接数: {len(self.pool)}")

    async def kick_one(self, ws: WebSocket):
        async with self._lock:
            for item in self.pool:
                if item[0] == ws:
                    self.pool.remove(item)
                    print(f"[WS] {item[2]} 断开了, 当前连接数: {len(self.pool)}")
                    break

    async def blast(self, msg: dict):
        """广播消息给所有在线客户端"""
        raw = json.dumps(msg, ensure_ascii=False)
        dead = []
        async with self._lock:
            for ws, _, _ in self.pool:
                try:
                    await ws.send_text(raw)
                except Exception:
                    dead.append(ws)
            # 清理死连接
            for d in dead:
                for item in self.pool:
                    if item[0] == d:
                        self.pool.remove(item)
                        break

    async def get_count(self):
        async with self._lock:
            return len(self.pool)

ws_pool = WSManager()
