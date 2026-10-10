# -*- coding: utf-8 -*-
"""
MCP 工具装载器：把注册表（mcp-servers.json）中「已启用」的 MCP server
的工具，经 langchain_mcp_adapters 转换为 LangChain tools 并缓存。

为什么是「异步刷新 + 缓存读取」：
- AgentHolder._build() 是同步调用（get() 处于事件循环内，无法再 await），
  而 MultiServerMCPClient.get_tools() 是协程（要建联并 tools/list）。
- 故工具装载只发生在可 await 的时机：服务启动（app lifespan）与
  MCP 注册表变更（mcp_api CRUD 后调用 refresh_and_invalidate），
  agent 构建时仅读取缓存列表。

失败隔离：逐个 server 独立装载，单个 server 不可达只记 warning 并跳过，
不阻塞其余 server 与 agent 构建。

循环导入约束：本模块顶层不得 import agent.engine / server.mcp_api
（engine 顶层 import 本模块），两者均在函数内延迟导入。
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# 单 server 装载超时（秒）：含 stdio 拉起子进程 / 远程建联 + initialize + tools/list
_LOAD_TIMEOUT = 30.0

# 模块级缓存：refresh() 成功后整体替换；get_mcp_tools() 只读
_tools: list = []


def _connection_of(s: dict) -> dict:
    """注册记录 -> langchain_mcp_adapters 连接配置。

    env 合并系统环境：stdio 子进程需要 PATH/SYSTEMROOT 等基础变量，
    只传注册表里的 API_KEY 会导致 npx/uvx 找不到而装载失败。
    """
    from server.mcp_api import _stdio_env  # 延迟导入：避免模块级循环依赖

    transport = s.get("transport", "stdio")
    if transport == "stdio":
        return {
            "transport": "stdio",
            "command": s.get("command", ""),
            "args": list(s.get("args", [])),
            "env": _stdio_env(s.get("env") or {}),
        }
    conn = {"transport": transport, "url": s.get("url", "")}
    if s.get("headers"):
        conn["headers"] = dict(s["headers"])
    return conn


async def _load_one(server: dict) -> list:
    """装载单个 server 的工具；任何异常向上抛由调用方隔离。"""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({server["name"]: _connection_of(server)})
    async with asyncio.timeout(_LOAD_TIMEOUT):
        return await client.get_tools()


async def refresh() -> int:
    """从注册表重新装载全部「已启用」server 的工具并更新缓存，返回工具总数。

    注意：仅 enabled=true 的 server 参与装载；停用的 server 工具不进入 agent。
    """
    global _tools
    from server.mcp_api import _load_registry  # 延迟导入：避免模块级循环依赖

    servers = [s for s in _load_registry() if s.get("enabled")]
    if not servers:
        _tools = []
        return 0

    try:
        import langchain_mcp_adapters  # noqa: F401
    except ImportError as e:
        logger.warning(f"langchain_mcp_adapters 不可用，跳过 MCP 工具装载：{e}")
        return len(_tools)

    new_tools: list = []
    # 已占用名字：先收集内置工具同名冲突防护所需，再随装载滚动更新
    used = {t.name for t in new_tools}
    failed: list[str] = []
    for server in servers:
        try:
            tools = await _load_one(server)
        except Exception as e:
            failed.append(server.get("name", "?"))
            logger.warning(f"MCP server「{server.get('name')}」工具装载失败：{type(e).__name__}: {e}")
            continue
        for t in tools:
            # 跨 server 重名时以「server名_工具名」加前缀；仍冲突则跳过（防御性）
            if t.name in used:
                prefixed = f"{server['name']}_{t.name}"
                if prefixed in used:
                    logger.warning(f"MCP 工具重名且加前缀仍冲突，跳过：{server['name']}/{t.name}")
                    continue
                t.name = prefixed
            used.add(t.name)
            new_tools.append(t)
    _tools = new_tools
    logger.info(
        f"MCP 工具装载完成：{len(new_tools)} 个工具，来自 {len(servers) - len(failed)}/{len(servers)} 个启用的 server"
        + (f"（失败：{', '.join(failed)}）" if failed else "")
    )
    return len(new_tools)


def get_mcp_tools() -> list:
    """agent 构建入口：返回当前缓存的 MCP 工具（同步、零 IO）。"""
    return list(_tools)


async def refresh_and_invalidate() -> int:
    """注册表变更后调用：刷新工具缓存并令 agent 失效（下一轮对话重建生效）。"""
    count = await refresh()
    from agent.engine import holder  # 延迟导入：engine 顶层 import 本模块

    holder.invalidate()
    return count
