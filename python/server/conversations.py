# -*- coding: utf-8 -*-
"""
会话（对话）元数据管理：JSON 文件持久化。

- 存储位置：用户数据目录（paths.data_dir，Electron userData），不放 runtime/（agent sandbox）
- 消息本体由 LangGraph checkpointer 按 thread_id 持久化，本模块只存少量关键信息：
  会话 id（即 thread_id）、标题、创建/更新时间、激活会话
- 写入策略：进程内锁 + 临时文件 os.replace 原子替换，避免半写状态
"""

import json
import logging
import os
import threading
import time
import uuid

import paths

logger = logging.getLogger(__name__)

FILE_NAME = "conversations.json"
TITLE_MAX = 24  # 自动标题取首条用户消息前 N 字符

_lock = threading.Lock()
_cache: dict | None = None  # 内存缓存：{version, activeId, conversations:[...] }


def _file_path() -> str:
    return paths.data_path(FILE_NAME)


def _default_doc() -> dict:
    return {"version": 1, "activeId": None, "conversations": []}


def _load() -> dict:
    """读取（或惰性加载）元数据；文件缺失/损坏时回退默认并自动补建会话。"""
    global _cache
    if _cache is not None:
        return _cache
    doc = _default_doc()
    try:
        with open(_file_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and isinstance(raw.get("conversations"), list):
            doc = raw
            doc.setdefault("activeId", None)
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"conversations.json 解析失败，按空档处理（原文件已备份 .bak）: {e}")
        try:
            os.replace(_file_path(), _file_path() + ".bak")
        except OSError:
            pass
    # 首次使用（或 activeId 悬空）：自动创建一个默认会话，保证任何时刻都有激活会话
    ids = {c.get("id") for c in doc["conversations"]}
    if doc.get("activeId") not in ids:
        if doc["conversations"]:
            # activeId 指向被删会话：回退到最近更新的一条
            doc["activeId"] = sorted(doc["conversations"], key=lambda c: c.get("updatedAt", 0))[-1]["id"]
        else:
            conv = _new_conv("新对话")
            doc["conversations"].append(conv)
            doc["activeId"] = conv["id"]
            _save(doc)
    _cache = doc
    return doc


def _save(doc: dict) -> None:
    """原子写：临时文件 + os.replace。调用方须持有 _lock。"""
    tmp = _file_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _file_path())


def _new_conv(title: str) -> dict:
    now = int(time.time() * 1000)
    return {
        "id": "conv-" + uuid.uuid4().hex[:12],
        "title": title,
        "createdAt": now,
        "updatedAt": now,
    }


# ---------------- 对外 API（均为线程安全的同步函数） ----------------

def list_sorted() -> list[dict]:
    """全部会话，按 updatedAt 倒序（列表页展示顺序）。"""
    with _lock:
        doc = _load()
        return sorted(doc["conversations"], key=lambda c: c.get("updatedAt", 0), reverse=True)


def active_id() -> str:
    """当前激活会话 id（不存在则自动创建）。"""
    with _lock:
        return _load()["activeId"]


def get(conv_id: str) -> dict | None:
    with _lock:
        return next((c for c in _load()["conversations"] if c.get("id") == conv_id), None)


def create(title: str = "新对话", activate: bool = True) -> dict:
    """新建会话；默认置为激活。返回新会话对象。"""
    with _lock:
        doc = _load()
        conv = _new_conv(title)
        doc["conversations"].append(conv)
        if activate:
            doc["activeId"] = conv["id"]
        _save(doc)
        return conv


def set_active(conv_id: str) -> dict | None:
    """切换激活会话；id 不存在返回 None。"""
    with _lock:
        doc = _load()
        conv = next((c for c in doc["conversations"] if c.get("id") == conv_id), None)
        if conv is None:
            return None
        doc["activeId"] = conv_id
        _save(doc)
        return conv


def touch(conv_id: str) -> None:
    """更新会话 updatedAt（每轮消息调用，驱动列表排序）。"""
    with _lock:
        doc = _load()
        conv = next((c for c in doc["conversations"] if c.get("id") == conv_id), None)
        if conv is not None:
            conv["updatedAt"] = int(time.time() * 1000)
            _save(doc)


def rename(conv_id: str, title: str) -> dict | None:
    """重命名会话（手动改名或首条消息自动生成标题）。"""
    title = (title or "").strip()[:TITLE_MAX] or "新对话"
    with _lock:
        doc = _load()
        conv = next((c for c in doc["conversations"] if c.get("id") == conv_id), None)
        if conv is None:
            return None
        conv["title"] = title
        _save(doc)
        return conv


def auto_title(conv_id: str, first_user_text: str) -> dict | None:
    """新会话首条用户消息 -> 截断生成标题（仅当仍是默认标题时生效，避免覆盖手动改名）。

    返回：标题确实发生变更时返回更新后的会话；未变更（已有自定义标题）返回 None。
    """
    conv = get(conv_id)
    if conv is not None and conv.get("title") in ("新对话", ""):
        return rename(conv_id, (first_user_text or "").strip()[:TITLE_MAX] or "新对话")
    return None


def delete(conv_id: str) -> bool:
    """删除会话元数据（checkpoint 数据保留在 sqlite，不物理删除）。

    删除的是激活会话时，自动切换到最近更新的其他会话；列表空了则新建默认会话。
    返回是否真实删除；切换后的 activeId 用 active_id() 再取。
    """
    with _lock:
        doc = _load()
        before = len(doc["conversations"])
        doc["conversations"] = [c for c in doc["conversations"] if c.get("id") != conv_id]
        if len(doc["conversations"]) == before:
            return False
        if doc.get("activeId") == conv_id:
            if doc["conversations"]:
                doc["activeId"] = sorted(doc["conversations"], key=lambda c: c.get("updatedAt", 0))[-1]["id"]
            else:
                conv = _new_conv("新对话")
                doc["conversations"].append(conv)
                doc["activeId"] = conv["id"]
        _save(doc)
        return True
