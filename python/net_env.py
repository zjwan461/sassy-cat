# -*- coding: utf-8 -*-
"""代理环境变量清洗。

背景（真实故障）：Windows 上常见的 ``NO_PROXY`` 里会带 ``[::1]``、``10.101.*`` 这类
条目。httpx（被 openai / langchain / huggingface_hub 共用）会把每条 no_proxy 规则
当作 URL pattern 解析，遇到方括号 IPv6 或通配星号直接抛：

    InvalidURL: Invalid port: ':1]'

而这个异常发生在 **构造 HTTP 客户端** 的阶段，于是每一次模型调用都会失败，
前端只看到「生成失败，请重试」，很难定位到环境变量上。

处理策略：
- 只删除 httpx 无法解析的条目（方括号 IPv6、含 ``*`` 的通配符），
  其余条目原样保留，不改变代理路由语义（这些条目本来也永远匹配不上）；
- ``NO_PROXY`` 与 ``no_proxy`` 同时存在时统一成一份，避免重复解析；
- 幂等，可重复调用。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_applied = False

# 参与清洗的键：httpx 会同时读大写与 HTTP_PROXY 之外的 NO_PROXY/no_proxy
_NO_PROXY_KEYS = ("NO_PROXY", "no_proxy")


def _normalize_entry(entry: str) -> str | None:
    """把一条 no_proxy 规则规范成 httpx 可解析的形式；无法转换则返回 None。

    httpx 把规则当 URL pattern 解析，以下几类会直接抛 InvalidURL：
    - 方括号形式 IPv6：``[::1]``
    - 含通配符：``10.101.*``、``*.corp.com``
    - 裸 IPv6：``::1``

    其中回环通配（``127.*``）语义明确，直接换成 ``127.0.0.1`` 保留；
    其余无法无损转换的条目丢弃（它们原本就永远匹配不上）。
    """
    if not entry:
        return None
    if entry in ("127.*", "127.", "127.0.0.*"):
        return "127.0.0.1"
    if entry in ("[::1]", "::1"):
        # httpx 无法表示 IPv6 直连规则；本机访问通常已被 localhost 覆盖
        return None
    if "*" in entry:
        return None
    if entry.startswith("[") or entry.endswith("]"):
        return None
    # 裸 IPv6（多个冒号）：httpx 按 host:port 解析会失败
    if entry.count(":") > 1:
        return None
    return entry


def sanitize_no_proxy(value: str) -> tuple[str, list[str]]:
    """清洗一条 no_proxy 字符串，返回 (清洗后字符串, 被丢弃的条目)。"""
    if not value:
        return "", []
    kept: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for raw in value.replace(";", ",").split(","):
        entry = raw.strip()
        if not entry:
            continue
        normalized = _normalize_entry(entry)
        if normalized is None:
            dropped.append(entry)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        kept.append(normalized)
    return ",".join(kept), dropped


def apply() -> None:
    """清洗进程环境中的 no_proxy（幂等，服务启动时调用一次即可）。"""
    global _applied
    if _applied:
        return
    _applied = True

    merged: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()

    for key in _NO_PROXY_KEYS:
        value = os.environ.get(key)
        if not value:
            continue
        cleaned, lost = sanitize_no_proxy(value)
        dropped.extend(lost)
        for entry in cleaned.split(","):
            entry = entry.strip()
            if entry and entry not in seen:
                seen.add(entry)
                merged.append(entry)

    if not merged and not dropped:
        return

    final = ",".join(merged)
    for key in _NO_PROXY_KEYS:
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = final
    # 小写别名同步一份，兼容只读小写键的库
    os.environ["no_proxy"] = final

    unique_dropped = list(dict.fromkeys(dropped))
    if unique_dropped:
        logger.warning(
            "NO_PROXY 中有 %d 条规则无法被 HTTP 客户端解析，已忽略：%s",
            len(unique_dropped),
            ", ".join(unique_dropped),
        )
    logger.debug("NO_PROXY 已归一化：%s", final)