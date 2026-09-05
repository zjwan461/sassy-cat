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


def _emit_metrics():
    emit({
        'type': 'metrics',
        'ts': int(time.time() * 1000),
        'cpu': cpu.collect(),
        'memory': memory.collect(),
        'gpus': gpu.collect(),
        'disks': disks.collect()
    })


def run():
    """服务入口（阻塞主循环）"""
    logger.info('服务启动成功')
    logger.info(f'依赖状态 -> {describe()}')
    if not HAS_PSUTIL:
        logger.info('使用 wmic/PowerShell 零依赖回退采集')

    static_info.init()
    emit({'type': 'sysinfo', 'data': static_info.sysinfo_payload()})

    cpu.warmup()

    try:
        while True:
            started = time.time()
            _emit_metrics()
            # 扣除采集耗时，保持节奏稳定
            elapsed = time.time() - started
            time.sleep(max(0.2, METRICS_INTERVAL - elapsed))
    except KeyboardInterrupt:
        logger.info('收到退出信号，正在关闭...')
    except Exception as e:
        logger.error(f'发生错误: {e}')
        sys.exit(1)
    finally:
        shutdown()
        logger.info('服务已停止')
