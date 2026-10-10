# -*- coding: utf-8 -*-
"""
MCP（Model Context Protocol）服务注册与发现 REST API：

- GET    /api/mcp                 列出全部已注册的 MCP server
- POST   /api/mcp                 注册 MCP server（body: McpServerPayload）
- PUT    /api/mcp/{name}          更新 MCP server 配置
- DELETE /api/mcp/{name}          删除 MCP server 注册
- POST   /api/mcp/import          批量导入（粘贴 Claude Desktop / mcp.json 风格配置）
- POST   /api/mcp/{name}/test     连接测试 + 工具发现（tools/list），结果回写 lastTest

存储：单文件 JSON，位于用户数据目录（Windows 为 %APPDATA%\\sassy-cat）下的
mcp-servers.json。写盘采用「临时文件 + 原子替换」，读盘容错（损坏时备份重建）。

说明：本模块只负责 MCP server 注册信息的维护（增删改查、导入导出、连通性验证），
暂不接入 agent 运行时。transport 支持 stdio / sse / streamable_http，
字段命名与 langchain_mcp_adapters 的连接配置保持兼容，便于后续直接对接。
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import paths

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

# 注册表文件：用户数据目录下 mcp-servers.json
REGISTRY_NAME = "mcp-servers.json"

# server 名称：与技能名同规则（字母/数字/下划线开头，允许 - _ .）
_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$")

_TRANSPORTS = {"stdio", "sse", "streamable_http"}

# 连接测试超时（秒）：包含拉起子进程/建联 + initialize + tools/list
_TEST_TIMEOUT = 20.0

# 进程内写锁：串行化读-改-写，避免并发请求互相覆盖
_write_lock = asyncio.Lock()


def _registry_path() -> str:
    return paths.data_path(REGISTRY_NAME)


def _load_registry() -> list[dict]:
    """读取注册表；文件不存在返回空表，损坏则备份后按空表继续（不静默吞数据）。"""
    p = _registry_path()
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        backup = f"{p}.corrupt-{int(time.time())}"
        try:
            os.replace(p, backup)
            logger.warning(f"mcp-servers.json 解析失败，已备份到 {backup}：{e}")
        except OSError:
            logger.warning(f"mcp-servers.json 解析失败且备份失败：{e}")
        return []
    servers = data.get("servers") if isinstance(data, dict) else None
    if not isinstance(servers, list):
        return []
    return [s for s in servers if isinstance(s, dict) and s.get("name")]


def _save_registry(servers: list[dict]) -> None:
    """原子写盘：先写 .tmp 再 os.replace，避免中途崩溃留下半截 JSON。"""
    p = _registry_path()
    tmp = p + ".tmp"
    payload = {"version": 1, "updatedAt": int(time.time() * 1000), "servers": servers}
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


class McpServerPayload(BaseModel):
    name: str = Field(..., description="server 唯一标识")
    displayName: str = ""
    description: str = ""
    transport: str = Field("stdio", description="stdio | sse | streamable_http")
    command: str = Field("", description="stdio 启动命令")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict, description="环境变量（含 API Key 等）")
    url: str = Field("", description="sse / streamable_http 的服务地址")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP 附加头（含 Authorization 等）")
    enabled: bool = True


def _validated_name(name: str) -> str:
    name = (name or "").strip()
    if not name or ".." in name or not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="非法的 server 名称（仅限字母、数字、-、_、.）")
    return name


def _validate_payload(payload: McpServerPayload) -> dict:
    """规范化并校验配置，返回可直接入库的 dict。"""
    name = _validated_name(payload.name)
    transport = (payload.transport or "stdio").strip().lower()
    if transport not in _TRANSPORTS:
        raise HTTPException(status_code=400, detail=f"不支持的 transport：{transport}（可选 {sorted(_TRANSPORTS)}）")
    if transport == "stdio":
        if not payload.command.strip():
            raise HTTPException(status_code=400, detail="stdio 类型必须填写启动命令")
    else:
        url = payload.url.strip()
        if not url:
            raise HTTPException(status_code=400, detail=f"{transport} 类型必须填写服务 URL")
        if not re.match(r"^https?://", url, re.I):
            raise HTTPException(status_code=400, detail="URL 必须以 http:// 或 https:// 开头")
    return {
        "name": name,
        "displayName": (payload.displayName or "").strip() or name,
        "description": (payload.description or "").strip(),
        "transport": transport,
        "command": payload.command.strip() if transport == "stdio" else "",
        "args": [str(a) for a in payload.args] if transport == "stdio" else [],
        "env": {str(k): str(v) for k, v in payload.env.items()} if transport == "stdio" else {},
        "url": payload.url.strip() if transport != "stdio" else "",
        "headers": {str(k): str(v) for k, v in payload.headers.items()} if transport != "stdio" else {},
        "enabled": bool(payload.enabled),
    }


def _find(servers: list[dict], name: str) -> Optional[dict]:
    for s in servers:
        if s.get("name") == name:
            return s
    return None


def _card(s: dict) -> dict:
    """列表/详情返回的卡片结构：附带连接目标摘要，不回显 env/headers 明文。"""
    if s.get("transport") == "stdio":
        target = " ".join([s.get("command", "")] + list(s.get("args", []))).strip()
    else:
        target = s.get("url", "")
    return {**s, "target": target}


def _schedule_tools_refresh() -> None:
    """注册表变更后异步刷新 agent 侧 MCP 工具缓存（不阻塞当前 HTTP 响应）。

    装载需逐 server 建联（每个最长 30s），放进后台任务；刷新完成后
    refresh_and_invalidate 会令 agent 失效，下一轮对话自动带新工具列表。
    """
    async def _run():
        try:
            from agent.tools.mcp_tools import refresh_and_invalidate  # 延迟导入防循环
            await refresh_and_invalidate()
        except Exception:
            logger.exception("MCP 工具缓存刷新失败（注册表变更本身不受影响）")

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        pass  # 无运行中事件循环（CLI 调试场景），跳过


@router.get("")
async def list_servers():
    """列出全部已注册的 MCP server。"""
    servers = _load_registry()
    return {"items": [_card(s) for s in sorted(servers, key=lambda x: str(x.get("name", "")).lower())]}


@router.post("")
async def create_server(payload: McpServerPayload):
    """注册一个新的 MCP server。"""
    record = _validate_payload(payload)
    async with _write_lock:
        servers = _load_registry()
        if _find(servers, record["name"]):
            raise HTTPException(status_code=409, detail=f"server「{record['name']}」已存在")
        record["createdAt"] = int(time.time() * 1000)
        record["updatedAt"] = record["createdAt"]
        record["lastTest"] = None
        servers.append(record)
        _save_registry(servers)
    logger.info(f"MCP server 已注册: {record['name']}（{record['transport']}）")
    _schedule_tools_refresh()
    return {"status": "success", "name": record["name"]}


@router.put("/{name}")
async def update_server(name: str, payload: McpServerPayload):
    """更新既有 MCP server 配置（保留 createdAt 与 lastTest 历史）。"""
    old_name = _validated_name(name)
    record = _validate_payload(payload)
    async with _write_lock:
        servers = _load_registry()
        existing = _find(servers, old_name)
        if not existing:
            raise HTTPException(status_code=404, detail="server 不存在")
        if record["name"] != old_name and _find(servers, record["name"]):
            raise HTTPException(status_code=409, detail=f"server「{record['name']}」已存在")
        record["createdAt"] = existing.get("createdAt", int(time.time() * 1000))
        record["updatedAt"] = int(time.time() * 1000)
        # 连接配置有变化时旧测试结果与已发现的工具列表一并作废
        config_keys = ("transport", "command", "args", "env", "url", "headers")
        changed = any(existing.get(k) != record.get(k) for k in config_keys)
        record["lastTest"] = None if changed else existing.get("lastTest")
        record["tools"] = [] if changed else existing.get("tools", [])
        record["toolsDiscoveredAt"] = None if changed else existing.get("toolsDiscoveredAt")
        servers[servers.index(existing)] = record
        _save_registry(servers)
    logger.info(f"MCP server 已更新: {record['name']}")
    _schedule_tools_refresh()
    return {"status": "success", "name": record["name"]}


@router.delete("/{name}")
async def delete_server(name: str):
    """删除 MCP server 注册（仅移除登记信息，不影响任何本地程序）。"""
    name = _validated_name(name)
    async with _write_lock:
        servers = _load_registry()
        existing = _find(servers, name)
        if not existing:
            raise HTTPException(status_code=404, detail="server 不存在")
        servers.remove(existing)
        _save_registry(servers)
    logger.info(f"MCP server 已删除: {name}")
    _schedule_tools_refresh()
    return {"status": "success", "name": name}


class ImportPayload(BaseModel):
    content: str = Field(..., description="mcpServers / servers 风格的 JSON 文本")
    overwrite: bool = Field(False, description="同名 server 已存在时是否覆盖")


def _infer_transport(entry: dict) -> str:
    """按配置字段推断 transport：显式 type > url（默认 streamable_http）> command（stdio）。

    注意：新版 MCP 规范已用 streamable_http 取代 SSE 作为远程传输的推荐方案，
    官方远程 server（如 WebFetch）均为 streamable_http 端点，因此带 url 的
    条目默认推断为 streamable_http 而非 sse（连接测试失败时仍有自动回退兜底）。
    """
    t = str(entry.get("type") or entry.get("transport") or "").strip().lower()
    if t in ("streamable-http", "streamablehttp", "http"):
        return "streamable_http"
    if t in ("sse", "stdio"):
        return t
    return "streamable_http" if entry.get("url") else "stdio"


@router.post("/import")
async def import_servers(payload: ImportPayload):
    """批量导入：粘贴 Claude Desktop / mcp.json 风格配置，同名默认跳过。

    兼容两种顶层结构：{"mcpServers": {...}} 与 {"servers": {...}}；
    条目字段 command/args/env/url/headers/type 均可选，缺省时按字段推断。
    """
    try:
        data = json.loads(payload.content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败：{e}")
    entries = data.get("mcpServers") or data.get("servers") if isinstance(data, dict) else None
    if not isinstance(entries, dict) or not entries:
        raise HTTPException(status_code=400, detail="未找到 mcpServers / servers 配置段")
    imported, skipped = [], []
    async with _write_lock:
        servers = _load_registry()
        for raw_name, entry in entries.items():
            if not isinstance(entry, dict):
                skipped.append(f"{raw_name}（配置不是对象）")
                continue
            try:
                name = _validated_name(str(raw_name))
                record = _validate_payload(McpServerPayload(
                    name=name,
                    transport=_infer_transport(entry),
                    command=str(entry.get("command") or ""),
                    args=[str(a) for a in (entry.get("args") or [])],
                    env={str(k): str(v) for k, v in (entry.get("env") or {}).items()},
                    url=str(entry.get("url") or ""),
                    headers={str(k): str(v) for k, v in (entry.get("headers") or {}).items()},
                    enabled=bool(entry.get("enabled", True)),
                ))
            except HTTPException as e:
                skipped.append(f"{raw_name}（{e.detail}）")
                continue
            existing = _find(servers, name)
            if existing and not payload.overwrite:
                skipped.append(f"{name}（已存在，未勾选覆盖）")
                continue
            now = int(time.time() * 1000)
            record["createdAt"] = existing.get("createdAt", now) if existing else now
            record["updatedAt"] = now
            record["lastTest"] = None
            if existing:
                servers[servers.index(existing)] = record
            else:
                servers.append(record)
            imported.append(name)
        if imported:
            _save_registry(servers)
    logger.info(f"MCP 批量导入：成功 {len(imported)}，跳过 {len(skipped)}")
    if imported:
        _schedule_tools_refresh()
    return {"status": "success", "imported": imported, "skipped": skipped}


class TestResult(BaseModel):
    ok: bool
    latencyMs: int = 0
    usedTransport: str = ""  # 实际连通的传输；与注册值不同说明发生了回退
    serverInfo: dict[str, Any] = Field(default_factory=dict)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    error: str = ""


def _build_connection(s: dict) -> dict:
    """注册记录 -> langchain_mcp_adapters 连接配置（字段直接透传）。"""
    if s.get("transport") == "stdio":
        conn: dict[str, Any] = {"command": s.get("command", ""), "args": list(s.get("args", []))}
        if s.get("env"):
            conn["env"] = dict(s["env"])
        return conn
    conn = {"url": s.get("url", "")}
    if s.get("headers"):
        conn["headers"] = dict(s["headers"])
    return conn


def _flatten_error(e: BaseException, depth: int = 0) -> str:
    """展开 anyio/mcp TaskGroup 的 ExceptionGroup，递归提取真正的子异常信息。

    mcp 客户端基于 anyio task group，底层失败（如命令找不到、连接被拒）会被
    包裹成 "unhandled errors in a TaskGroup (1 sub-exception)"，必须解包到
    叶子异常才能给用户可操作的报错。
    """
    if depth > 6:
        return f"{type(e).__name__}: {e}"
    # ExceptionGroup（含 anyio 的 ExceptionGroup/BaseExceptionGroup）
    subs = getattr(e, "exceptions", None)
    if isinstance(subs, (list, tuple)) and subs:
        parts: list[str] = []
        for sub in subs:
            msg = _flatten_error(sub, depth + 1)
            if msg not in parts:  # 同一异常常被重复上报，去重
                parts.append(msg)
        return "; ".join(parts)
    msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
    cause = e.__cause__ or e.__context__
    if cause is not None and not isinstance(cause, type(e)):
        msg += f" <- {_flatten_error(cause, depth + 1)}"
    return msg


def _is_timeout_error(e: BaseException) -> bool:
    """超时判定：asyncio.timeout 触发的取消在 task group 关闭路径上可能被
    包裹/转译为普通 Exception，需递归检查异常树中是否含 TimeoutError。"""
    if isinstance(e, TimeoutError):
        return True
    subs = getattr(e, "exceptions", None)
    if isinstance(subs, (list, tuple)):
        return any(_is_timeout_error(sub) for sub in subs)
    cause = e.__cause__ or e.__context__
    return cause is not None and _is_timeout_error(cause)


def _stdio_env(user_env: dict) -> dict:
    """合并系统环境与注册配置 env：stdio 子进程需要 PATH/SYSTEMROOT 等基础变量，
    只传配置里的 API_KEY 会导致 npx/uvx 等启动命令找不到而失败。"""
    merged = dict(os.environ)
    merged.update({str(k): str(v) for k, v in (user_env or {}).items()})
    return merged

async def _probe_once(s: dict, transport: str) -> tuple[TestResult, BaseException | None]:
    """按指定 transport 单次建联：initialize 握手 + tools/list 工具发现。

    返回 (结果, 原始异常)：结果 ok=True 时异常为 None；连接类失败
    保留异常对象供上层判断是否做远程传输回退重试。
    """
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.sse import sse_client
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as e:
        return TestResult(ok=False, error=f"运行环境缺少 mcp 依赖：{e}"), None

    from contextlib import AsyncExitStack

    try:
        start = time.monotonic()
        async with asyncio.timeout(_TEST_TIMEOUT):
            stack = AsyncExitStack()
            try:
                if transport == "stdio":
                    params = StdioServerParameters(
                        command=s.get("command", ""),
                        args=list(s.get("args", [])),
                        env=_stdio_env(s.get("env") or {}),
                    )
                    client_cm = stdio_client(params)
                else:
                    client_factory = sse_client if transport == "sse" else streamablehttp_client
                    client_cm = client_factory(s.get("url", ""), headers=dict(s.get("headers") or {}) or None)
                # sse_client 返回 (read, write)；streamable_http 返回 (read, write, get_session_id)
                ctx = await stack.enter_async_context(client_cm)
                session = await stack.enter_async_context(ClientSession(ctx[0], ctx[1]))
                # 当前 mcp SDK 无 session.server_info 属性：服务端信息取自
                # initialize() 返回的 InitializeResult（serverInfo + protocolVersion）
                init_res = await session.initialize()
                tools_res = await session.list_tools()
                tools = [{"name": t.name, "description": t.description or ""} for t in tools_res.tools]
            finally:
                # 确保异常路径下也回收子进程/连接（stdio 子进程泄漏防护）
                await stack.aclose()
        latency = int((time.monotonic() - start) * 1000)
        server_impl = getattr(init_res, "serverInfo", None)
        return TestResult(
            ok=True,
            latencyMs=latency,
            usedTransport=transport,
            serverInfo={
                "name": getattr(server_impl, "name", "") or "",
                "version": getattr(server_impl, "version", "") or "",
                "protocolVersion": getattr(init_res, "protocolVersion", "") or "",
            },
            tools=tools,
        ), None
    except TimeoutError:
        return TestResult(ok=False, error=f"连接超时（>{int(_TEST_TIMEOUT)}s）"), None
    except Exception as e:
        detail = _flatten_error(e)
        # task group 包裹下超时可能以普通异常形态逃逸，按超时兜底展示
        if _is_timeout_error(e):
            detail = f"连接超时（>{int(_TEST_TIMEOUT)}s）"
        return TestResult(ok=False, error=detail), e


def _has_exception_named(e: BaseException, names: set[str], depth: int = 0) -> bool:
    """递归检查异常树（含 ExceptionGroup 子异常与 __cause__/__context__）中
    是否存在指定类名的异常。"""
    if depth > 6:
        return False
    if type(e).__name__ in names:
        return True
    subs = getattr(e, "exceptions", None)
    if isinstance(subs, (list, tuple)) and any(_has_exception_named(sub, names, depth + 1) for sub in subs):
        return True
    cause = e.__cause__ or e.__context__
    return cause is not None and _has_exception_named(cause, names, depth + 1)


def _is_transport_mismatch(exc: BaseException | None) -> bool:
    """判断异常是否属于「远程传输类型不匹配」：SSE 客户端收到非 event-stream
    响应（SSEError），或 streamable_http 收到非预期状态码（HTTPStatusError），
    均应回退用另一种远程传输重试。异常可能被 TaskGroup 包裹，需递归检查。"""
    return exc is not None and _has_exception_named(exc, {"SSEError", "HTTPStatusError"})


async def _probe_server(s: dict) -> TestResult:
    """真实建联探测；远程传输不匹配时自动用另一种（sse <-> streamable_http）重试。"""
    transport = s.get("transport", "stdio")
    result, exc = await _probe_once(s, transport)
    if not result.ok and transport in ("sse", "streamable_http") and _is_transport_mismatch(exc):
        alt = "streamable_http" if transport == "sse" else "sse"
        logger.info(f"MCP [{s.get('name')}] 按 {transport} 连接失败（{result.error}），回退 {alt} 重试")
        retry, _ = await _probe_once(s, alt)
        if retry.ok:
            return retry
        # 两种都失败：合并展示，引导用户改注册配置
        return TestResult(
            ok=False,
            error=f"{transport} 与 {alt} 均连接失败：{result.error}；（回退）{retry.error}",
        )
    if not result.ok:
        logger.warning(f"MCP 连接测试失败 [{s.get('name')}]: {result.error}")
    return result


@router.post("/{name}/test")
async def test_server(name: str):
    """连接测试 + 工具发现，结果回写注册表 lastTest 与 tools 字段。

    工具列表仅在测试成功时更新并持久化（下次进页面无需重新建联即可展示）；
    失败时保留历史发现结果，只刷新 lastTest 状态，便于对照排查。
    """
    name = _validated_name(name)
    servers = _load_registry()
    existing = _find(servers, name)
    if not existing:
        raise HTTPException(status_code=404, detail="server 不存在")
    result = await _probe_server(existing)
    # 回写测试结果（失败也记录，便于界面展示最近一次探测状态）
    async with _write_lock:
        servers = _load_registry()
        existing = _find(servers, name)
        if existing:
            now = int(time.time() * 1000)
            existing["lastTest"] = {
                "at": now,
                "ok": result.ok,
                "latencyMs": result.latencyMs,
                "toolCount": len(result.tools),
                # 实际连通的传输与注册值不同 => 测试时发生了回退，提示用户更新注册配置
                "usedTransport": result.usedTransport,
                "mismatch": bool(result.ok and result.usedTransport and result.usedTransport != existing.get("transport")),
                "error": result.error,
            }
            if result.ok:
                existing["tools"] = result.tools
                existing["toolsDiscoveredAt"] = now
            _save_registry(servers)
    return result.model_dump()


@router.get("/export")
async def export_servers(
    names: str = Query("", description="逗号分隔的 server 名，缺省导出全部"),
):
    """导出注册表为 mcpServers 风格 JSON（含 env/headers 明文，注意保管）。"""
    servers = _load_registry()
    wanted = {n.strip() for n in names.split(",") if n.strip()}
    selected = [s for s in servers if not wanted or s["name"] in wanted]
    if wanted and len(selected) != len(wanted):
        missing = wanted - {s["name"] for s in selected}
        raise HTTPException(status_code=404, detail=f"server 不存在：{', '.join(sorted(missing))}")
    out: dict[str, Any] = {}
    for s in selected:
        entry: dict[str, Any] = {"type": s["transport"]}
        if s["transport"] == "stdio":
            entry["command"] = s.get("command", "")
            if s.get("args"):
                entry["args"] = s["args"]
            if s.get("env"):
                entry["env"] = s["env"]
        else:
            entry["url"] = s.get("url", "")
            if s.get("headers"):
                entry["headers"] = s["headers"]
        entry["enabled"] = bool(s.get("enabled", True))
        out[s["name"]] = entry
    return {"mcpServers": out}
