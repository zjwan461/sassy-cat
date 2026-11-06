# -*- coding: utf-8 -*-
"""
服务端事件总线与会话房间管理。

- 房间（Room）：同一 sessionId 下的所有 WS 连接（桌宠 / 主窗口 / Electron 系统连接）
- publish(session_id, frame)：向房间内除来源外的所有连接 fan-out
- 系统事件（无 session）：publish_system 广播给所有连接

发送策略：
- 广播前先把帧序列化一次（多个连接不再各自 json.dumps）；
- 多个连接并发发送，避免一个慢连接把整条流式输出拖住；
- 单连接发送超时（默认 2s）只记日志、不阻塞其它连接。
"""

import asyncio
import json
import logging
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# 单连接单帧发送上限：正常本地 WS 是毫秒级，超过说明对端卡死/管道堵塞
_SEND_TIMEOUT = 2.0


class Hub:
    def __init__(self):
        self._rooms: dict[str, Set[WebSocket]] = {}
        self._all: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def join(self, session_id: str, ws: WebSocket):
        async with self._lock:
            self._rooms.setdefault(session_id, set()).add(ws)
            self._all.add(ws)

    async def leave(self, session_id: str | None, ws: WebSocket):
        async with self._lock:
            self._all.discard(ws)
            if session_id and session_id in self._rooms:
                self._rooms[session_id].discard(ws)
                if not self._rooms[session_id]:
                    del self._rooms[session_id]

    async def move_room(self, old_id: str, new_id: str):
        """把旧房间全部连接迁移到新房间（切换激活会话时，多窗口无需重连即同步换房）"""
        async with self._lock:
            conns = self._rooms.pop(old_id, set())
            if conns:
                self._rooms.setdefault(new_id, set()).update(conns)

    async def _send_text(self, ws: WebSocket, payload: str) -> None:
        try:
            await asyncio.wait_for(ws.send_text(payload), timeout=_SEND_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("WS 发送超时（%.1fs），跳过该帧；对端可能已卡死", _SEND_TIMEOUT)
        except Exception:
            logger.debug("发送失败，连接可能已关闭", exc_info=True)

    async def _broadcast(self, frame: dict, targets, exclude: WebSocket | None):
        if not targets:
            return
        # 只序列化一次：流式场景下每帧可能同时发给主窗口 + 桌宠
        payload = json.dumps(frame, ensure_ascii=False, default=str)
        await asyncio.gather(
            *(self._send_text(ws, payload) for ws in targets if ws is not exclude)
        )

    async def publish(self, session_id: str, frame: dict, exclude: WebSocket | None = None):
        """向会话房间广播；exclude 用于不回显来源连接"""
        await self._broadcast(frame, list(self._rooms.get(session_id, ())), exclude)

    async def publish_all(self, frame: dict, exclude: WebSocket | None = None):
        await self._broadcast(frame, list(self._all), exclude)

    def active_sessions(self) -> set:
        """当前有活跃连接的 session 集合（proactive 判定用）"""
        return {sid for sid, conns in self._rooms.items() if conns}


hub = Hub()
