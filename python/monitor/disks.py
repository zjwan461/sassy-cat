# -*- coding: utf-8 -*-
"""磁盘指标采集：psutil 优先，回退 wmic logicaldisk"""

from . import shell
from .deps import IS_WINDOWS, HAS_PSUTIL, psutil


def collect():
    disks = []
    if HAS_PSUTIL:
        seen = set()
        for part in psutil.disk_partitions(all=False):
            key = part.device.lower() if IS_WINDOWS else part.mountpoint
            if key in seen:
                continue
            seen.add(key)
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            disks.append({
                'mount': part.mountpoint,
                'percent': round(usage.percent, 1),
                'totalGB': round(usage.total / 1024 ** 3, 1),
                'usedGB': round(usage.used / 1024 ** 3, 1)
            })
        return disks

    if IS_WINDOWS:
        out = shell.run('wmic logicaldisk get Caption,FreeSpace,Size /value')
        if out:
            entries = []
            cur = {}
            for line in out.splitlines():
                line = line.strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    cur[k.strip()] = v.strip()
                elif cur:
                    entries.append(cur)
                    cur = {}
            if cur:
                entries.append(cur)
            for e in entries:
                try:
                    size = float(e.get('Size') or 0)
                    free = float(e.get('FreeSpace') or 0)
                    if size <= 0:
                        continue
                    mount = e.get('Caption', '?')
                    disks.append({
                        'mount': mount + '\\',
                        'percent': round((size - free) / size * 100, 1),
                        'totalGB': round(size / 1024 ** 3, 1),
                        'usedGB': round((size - free) / 1024 ** 3, 1)
                    })
                except Exception:
                    continue
    return disks
