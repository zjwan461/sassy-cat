# -*- coding: utf-8 -*-
"""CPU 指标采集：psutil 优先，回退 wmic LoadPercentage"""

from . import shell, static_info
from .deps import IS_WINDOWS, HAS_PSUTIL, psutil


def warmup():
    """预热 psutil cpu_percent（首次调用返回 0，需先调用一次丢弃）"""
    if HAS_PSUTIL:
        psutil.cpu_percent(interval=None)


def collect():
    static = static_info.get()
    if HAS_PSUTIL:
        percent = psutil.cpu_percent(interval=None)
        return {
            'percent': round(percent, 1),
            'cores': static.get('cpuCores'),
            'threads': static.get('cpuThreads')
        }
    if IS_WINDOWS:
        kv = shell.wmic_kv('wmic cpu get LoadPercentage /value')
        if kv.get('LoadPercentage'):
            return {
                'percent': float(kv['LoadPercentage']),
                'cores': static.get('cpuCores'),
                'threads': static.get('cpuThreads')
            }
    return None
