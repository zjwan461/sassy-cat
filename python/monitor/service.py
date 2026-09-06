# -*- coding: utf-8 -*-
"""
监控服务主循环：
  启动 -> 采集静态信息并上报 sysinfo -> 周期采集并上报 metrics
"""

import logging
import sys
import time

from . import cpu, disks, gpu, memory, static_info
from .deps import describe, shutdown, HAS_PSUTIL
from .protocol import emit

logger = logging.getLogger(__name__)

# 监控上报间隔（秒）
METRICS_INTERVAL = 2

# 最新一次采集的 metrics 缓存（供 asyncio 周期任务与 WS metrics.snapshot 使用）
_latest_metrics = None


def collect_payload():
    """执行一次全量采集，返回 metrics payload（阻塞调用，供 asyncio.to_thread 包装）"""
    return {
        'type': 'metrics',
        'ts': int(time.time() * 1000),
        'cpu': cpu.collect(),
        'memory': memory.collect(),
        'gpus': gpu.collect(),
        'disks': disks.collect()
    }


def latest_metrics():
    return _latest_metrics


def collect_once_and_emit():
    """采集一次、更新缓存并向 stdout 打印协议行（兼容现有 Electron 解析）"""
    global _latest_metrics
    payload = collect_payload()
    _latest_metrics = payload
    emit(payload)
    return payload


def init_sync():
    """同步初始化：依赖日志、静态信息采集与上报、CPU warmup"""
    logger.info('服务启动成功')
    logger.info(f'依赖状态 -> {describe()}')
    if not HAS_PSUTIL:
        logger.info('使用 wmic/PowerShell 零依赖回退采集')

    static_info.init()
    emit({'type': 'sysinfo', 'data': static_info.sysinfo_payload()})
    cpu.warmup()


def shutdown_sync():
    shutdown()


def run():
    """旧版阻塞入口（保留兼容，正常启动路径见 python/main.py 的 asyncio 模型）"""
    init_sync()
    try:
        while True:
            started = time.time()
            collect_once_and_emit()
            # 扣除采集耗时，保持节奏稳定
            elapsed = time.time() - started
            time.sleep(max(0.2, METRICS_INTERVAL - elapsed))
    except KeyboardInterrupt:
        logger.info('收到退出信号，正在关闭...')
    except Exception as e:
        logger.error(f'发生错误: {e}')
        sys.exit(1)
    finally:
        shutdown_sync()
        logger.info('服务已停止')
        logger.info('服务已停止')
