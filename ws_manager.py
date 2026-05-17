# WebSocket 连接池 - 异步非阻塞广播 + Token过期检测
from fastapi import WebSocket
import json
import asyncio
import time

WS_SEND_TIMEOUT = 2.0  # 单条消息发送超时

class WSManager:
    """管所有 ws 连接 + 广播（异步非阻塞，单点失败不影响其他）"""

    def __init__(self):
        self.pool = []  # [(ws, uid, uname, token_exp), ...]
        self._lock = asyncio.Lock()

    async def add_one(self, ws: WebSocket, uid: int, uname: str, token_exp: float = 0):
        async with self._lock:
            self.pool.append((ws, uid, uname, token_exp))
            print(f"[WS] {uname} 连上了, 当前连接数: {len(self.pool)}")

    async def kick_one(self, ws: WebSocket):
        async with self._lock:
            for item in self.pool:
                if item[0] == ws:
                    self.pool.remove(item)
                    print(f"[WS] {item[2]} 断开了, 当前连接数: {len(self.pool)}")
                    break

    async def blast(self, msg: dict):
        """异步非阻塞广播 - 每个连接独立发送，2秒超时，单失败不影响其他"""
        raw = json.dumps(msg, ensure_ascii=False)
        dead = []

        async with self._lock:
            items = list(self.pool)

        # 不持锁发送，每个连接独立 task
        async def send_one(ws, idx):
            try:
                await asyncio.wait_for(ws.send_text(raw), timeout=WS_SEND_TIMEOUT)
                return idx, True
            except Exception:
                return idx, False

        tasks = [asyncio.create_task(send_one(ws, i)) for i, (ws, _, _, _) in enumerate(items)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        async with self._lock:
            for r in results:
                if isinstance(r, tuple) and not r[1]:
                    dead.append(items[r[0]][0])
            for d in dead:
                for item in self.pool:
                    if item[0] == d:
                        self.pool.remove(item)
                        break

    async def get_count(self):
        async with self._lock:
            return len(self.pool)

    async def check_token_expiry(self):
        """检查所有连接的 token 是否过期，过期就踢"""
        now = time.time()
        expired = []
        async with self._lock:
            for ws, uid, uname, exp in self.pool:
                if exp and now > exp:
                    expired.append((ws, uname))
        for ws, uname in expired:
            try:
                await ws.send_text(json.dumps({"type": "token_expired", "msg": "token过期，请重新登录"}))
                await ws.close()
            except Exception:
                pass
            await self.kick_one(ws)

    async def update_token_exp(self, ws: WebSocket, new_exp: float):
        async with self._lock:
            for i, item in enumerate(self.pool):
                if item[0] == ws:
                    self.pool[i] = (item[0], item[1], item[2], new_exp)
                    break

ws_pool = WSManager()
