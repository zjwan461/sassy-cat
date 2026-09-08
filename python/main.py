#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python 后端服务入口（由 Electron 主进程启动）

单进程 asyncio 模型（设计稿 1.3 节）：
  server/app.py      FastAPI：/health、/ws/agent、lifespan 后台任务
  monitor/service.py 周期采集（to_thread 包装阻塞调用），同时保留 stdout __PROTOCOL__ 行兼容
  proactive/         闲置提醒调度
  agent/             deepagents 引擎（engine=AgentHolder, runner=流式桥接）

启动参数：
  --config <path>    用户配置文件（config.user.json，Electron userData 下）
  --data-dir <path>  用户数据目录（Electron app.getPath('userData')，存会话元数据与 checkpoint）
就绪信号：stdout 打印 `[READY] {"port": ...}`，Electron 据此广播 agent-ready。
"""

import argparse
import asyncio
import json
import logging
import os
import socket
import sys

# 确保以任意工作目录启动时都能导入本目录下的包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
)

# 将 logging 记录同时转发为 __PROTOCOL__ log 行，经 Electron 推送到前端日志页
from monitor.protocol import ProtocolLogHandler  # noqa: E402

_protocol_handler = ProtocolLogHandler()
_protocol_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(_protocol_handler)

logger = logging.getLogger('main')


def _find_free_port(preferred: int) -> int:
    """优先使用配置端口，被占用则回退到临时可用端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', preferred))
            return preferred
        except OSError:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]


def _emit_ready(port: int):
    print(f'[READY] {json.dumps({"port": port})}', flush=True)


async def main():
    parser = argparse.ArgumentParser(description='sassy-cat python backend')
    parser.add_argument('--config', default=os.getenv('SASSY_CAT_CONFIG'), help='config.user.json 路径')
    parser.add_argument('--data-dir', default=None, help='用户数据目录（userData）')
    args = parser.parse_args()

    # 先初始化数据目录（含 runtime 旧 checkpoint 搬迁），后续 constant 派生 DB_URL 依赖它
    import paths
    paths.init(args.data_dir)

    import config_loader
    cfg = config_loader.load_config(args.config)

    # 延迟导入，确保 config_loader 先就绪
    import uvicorn
    from server.app import create_app

    preferred = int(cfg.get('server.wsPort', 8790))
    host = cfg.get('server.host', '127.0.0.1')
    port = _find_free_port(preferred)
    if port != preferred:
        logger.warning(f'端口 {preferred} 被占用，回退到 {port}')

    app = create_app()
    uv_config = uvicorn.Config(
        app, host=host, port=port, log_level='info',
        # uvicorn 默认会接管日志；保留其访问日志关闭减少 stdout 噪音
        access_log=False,
    )
    server = uvicorn.Server(uv_config)

    # 服务真正开始监听后再发 READY：用 should_exit 之前的首次循环近似
    async def ready_watcher():
        while not server.started:
            await asyncio.sleep(0.1)
        _emit_ready(port)

    watcher = asyncio.create_task(ready_watcher())
    try:
        await server.serve()
    finally:
        watcher.cancel()


if __name__ == '__main__':
    print(f'[INFO] Python 版本: {sys.version.split()[0]}', flush=True)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('收到退出信号，正在关闭...')
