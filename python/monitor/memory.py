# -*- coding: utf-8 -*-
"""内存指标采集：psutil 优先，回退 wmic OS 物理内存"""

from . import shell
from .deps import IS_WINDOWS, HAS_PSUTIL, psutil


def collect():
    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        return {
            'percent': round(mem.percent, 1),
            'totalGB': round(mem.total / 1024 ** 3, 1),
            'usedGB': round(mem.used / 1024 ** 3, 1)
        }
    if IS_WINDOWS:
        kv = shell.wmic_kv('wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /value')
        try:
            total_kb = int(kv['TotalVisibleMemorySize'])
            free_kb = int(kv['FreePhysicalMemory'])
            total_gb = total_kb / 1024 / 1024
            used_gb = (total_kb - free_kb) / 1024 / 1024
            return {
                'percent': round((total_kb - free_kb) / total_kb * 100, 1),
                'totalGB': round(total_gb, 1),
                'usedGB': round(used_gb, 1)
            }
        except Exception:
            pass
    return None
