# -*- coding: utf-8 -*-
"""
服务端事件总线与会话房间管理。

- 房间（Room）：同一 sessionId 下的所有 WS 连接（桌宠 / 主窗口 / Electron 系统连接）
- publish(session_id, frame)：向房间内除来源外的所有连接 fan-out
- 系统事件（无 session）：publish_system 广播给所有连接
"""

import asyncio
import logging
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


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

    async def publish(self, session_id: str, frame: dict, exclude: WebSocket | None = None):
        """向会话房间广播；exclude 用于不回显来源连接"""
        targets = list(self._rooms.get(session_id, ()))
        for ws in targets:
            if ws is exclude:
                continue
            try:
                await ws.send_json(frame)
            except Exception:
                logger.debug("fan-out 失败，连接可能已关闭", exc_info=True)

    async def publish_all(self, frame: dict, exclude: WebSocket | None = None):
        for ws in list(self._all):
            if ws is exclude:
                continue
            try:
                await ws.send_json(frame)
            except Exception:
                logger.debug("broadcast 失败", exc_info=True)

    def active_sessions(self) -> set:
        """当前有活跃连接的 session 集合（proactive 判定用）"""
        return {sid for sid, conns in self._rooms.items() if conns}


hub = Hub()
