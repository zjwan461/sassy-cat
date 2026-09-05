# -*- coding: utf-8 -*-
"""
GPU 指标采集（自动降级）：
  1. NVML（pynvml）—— NVIDIA 精确利用率与显存
  2. PDH（pywin32 win32pdh）—— Windows 性能计数器，支持 AMD/Intel
  3. PowerShell Get-Counter —— 零依赖回退
"""

import re
import time

from . import shell, static_info
from .deps import (
    IS_WINDOWS, HAS_NVML, pynvml, HAS_PDH
)

# PowerShell GPU 采集脚本（PDH 不可用时的回退）
_PS_GPU_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$u=(Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage').CounterSamples;"
    "$u|Group-Object{if($_.InstanceName -match 'luid_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+'){$Matches[0]}else{'na'}}|ForEach-Object{"
    "$s=($_.Group|Measure-Object CookedValue -Sum).Sum;"
    "Write-Output ('U;'+$_.Name+';'+[math]::Round($s,1))};"
    "$m=(Get-Counter '\\GPU Adapter Memory(*\\*)\\Total Dedicated Bytes').CounterSamples;"
    "$m|Where-Object{$_.InstanceName -match 'phys_local'}|Group-Object{if($_.InstanceName -match 'luid_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+'){$Matches[0]}else{'na'}}|ForEach-Object{"
    "$s=($_.Group|Measure-Object CookedValue -Sum).Sum;"
    "Write-Output ('M;'+$_.Name+';'+[math]::Round($s,0))}"
)


def _collect_nvml():
    """NVIDIA GPU（NVML）"""
    gpus = []
    if not HAS_NVML:
        return gpus
    try:
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            try:
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode('utf-8', errors='replace')
            except Exception:
                name = 'Unknown GPU'
            gpus.append({
                'name': name,
                'vendor': shell.classify_vendor(name),
                'percent': round(util.gpu, 1),
                'memTotalGB': round(mem.total / 1024 ** 3, 1),
                'memUsedGB': round(mem.used / 1024 ** 3, 1),
                'source': 'nvml'
            })
    except Exception:
        pass
    return gpus


# ---------- PDH（pywin32）路径 ----------

def _pdh_collect(counter_set: str, counter_name: str, instance_filter=None):
    """通用 PDH 采集：返回 {instanceName: value}"""
    try:
        import pythoncom  # noqa: F401
        import win32pdh
    except ImportError:
        return {}
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass
    result = {}
    query = None
    try:
        query = win32pdh.OpenQuery(None)
        counter_list, _ = win32pdh.EnumObjectItems(
            None, None, counter_set, win32pdh.PERF_DETAIL_WIZARD)
        cums = {}
        for name in counter_list:
            if instance_filter and not instance_filter(name):
                continue
            try:
                path = win32pdh.MakeCounterPath(
                    (None, counter_set, name, None, -1, counter_name))
                cums[name] = win32pdh.AddCounter(query, path)
            except Exception:
                continue
        if not cums:
            return {}
        win32pdh.CollectData(query)
        time.sleep(0.3)
        win32pdh.CollectData(query)
        for name, h in cums.items():
            try:
                items = win32pdh.GetFormattedCounterValueDouble(query, h)
                total = sum(v for _, v in items)
                if total > 0:
                    result[name] = total
            except Exception:
                continue
    except Exception:
        pass
    finally:
        if query is not None:
            try:
                win32pdh.CloseQuery(query)
            except Exception:
                pass
    return result


def _luid_of(instance_name: str):
    m = re.search(r'luid_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+', instance_name)
    return m.group(0) if m else None


def _aggregate_by_luid(samples):
    """{instance: value} -> {luid: sum}"""
    agg = {}
    for inst, v in samples.items():
        luid = _luid_of(inst)
        if luid:
            agg[luid] = agg.get(luid, 0.0) + v
    return agg


def _collect_pdh():
    """PDH 采集 GPU 利用率与显存（支持 AMD/Intel/NVIDIA）"""
    util_samples = _pdh_collect(
        '\\GPU Engine', 'Utilization Percentage',
        lambda n: 'engtype_3D' in n)
    mem_samples = _pdh_collect(
        '\\GPU Adapter Memory', 'Total Dedicated Bytes',
        lambda n: 'phys_local' in n)
    return _aggregate_by_luid(util_samples), _aggregate_by_luid(mem_samples)


# ---------- PowerShell 零依赖回退 ----------

def _collect_powershell():
    """PowerShell Get-Counter 回退（无任何第三方依赖）"""
    out = shell.run_powershell(_PS_GPU_SCRIPT, timeout=12.0)
    utils, mems = {}, {}
    if not out:
        return utils, mems
    for line in out.splitlines():
        parts = line.strip().split(';')
        if len(parts) != 3:
            continue
        kind, luid, val = parts
        if luid == 'na':
            continue
        try:
            v = float(val.replace(',', ''))
            if kind == 'U':
                utils[luid] = utils.get(luid, 0.0) + v
            elif kind == 'M':
                mems[luid] = max(mems.get(luid, 0.0), v)
        except ValueError:
            continue
    return utils, mems


# ---------- 统一入口 ----------

def collect():
    """
    统一 GPU 采集入口（自动降级）：
    NVML -> PDH(pywin32) -> PowerShell Get-Counter
    """
    gpus = _collect_nvml()

    if IS_WINDOWS:
        static = static_info.get()
        names = static.get('gpuNames') or []
        nvml_names = {g['name'] for g in gpus}
        remaining = [n for n in names if n not in nvml_names]

        utils, mems = ({}, {})
        if HAS_PDH:
            utils, mems = _collect_pdh()
        if not utils and not mems:
            utils, mems = _collect_powershell()

        if utils or mems:
            luids = sorted(set(list(utils.keys()) + list(mems.keys())))
            # 一块物理显卡常对应多个 LUID（每驱动进程上下文一个）。
            # 非 NVML 卡数量 <= 1 时（绝大多数单卡场景），合并所有 LUID 数据。
            if len(remaining) <= 1:
                util = min(100.0, round(sum(utils.values()), 1))
                mem_bytes = max(mems.values()) if mems else None
                name = remaining[0] if remaining else 'GPU'
                gpus.append({
                    'name': name,
                    'vendor': shell.classify_vendor(name),
                    'percent': util,
                    'memTotalGB': static.get('gpuMemGB', {}).get(name),
                    'memUsedGB': round(mem_bytes / 1024 ** 3, 1) if mem_bytes else None,
                    'source': 'pdh' if HAS_PDH else 'powershell'
                })
            else:
                # 多卡：按 LUID 负载从高到低与卡名从高到低近似对应
                ordered = sorted(luids, key=lambda l: utils.get(l, 0.0), reverse=True)
                for idx, luid in enumerate(ordered[:len(remaining)]):
                    name = remaining[idx]
                    gpus.append({
                        'name': name,
                        'vendor': shell.classify_vendor(name),
                        'percent': min(100.0, round(utils.get(luid, 0.0), 1)),
                        'memTotalGB': static.get('gpuMemGB', {}).get(name),
                        'memUsedGB': round(mems[luid] / 1024 ** 3, 1) if mems.get(luid) else None,
                        'source': 'pdh' if HAS_PDH else 'powershell'
                    })
    return gpus
