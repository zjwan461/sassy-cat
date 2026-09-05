# -*- coding: utf-8 -*-
"""
静态信息采集（启动时采集一次并缓存）：
CPU 名称/核数、GPU 名称与显存总量、内存总量、启动时间等。
采集链：psutil -> wmic -> PowerShell Get-CimInstance；GPU 名称另走 NVML -> WMI -> wmic。
"""

import socket
import platform
import time

from . import shell
from .deps import IS_WINDOWS, HAS_PSUTIL, psutil, HAS_NVML, pynvml, HAS_WMI, WMI_CLIENT

# 模块级缓存
_STATIC = {}


def collect():
    """采集 CPU 名称/核数、GPU 名称列表、内存总量等静态信息"""
    info = {
        'hostname': socket.gethostname(),
        'osName': f'{platform.system()} {platform.release()}',
        'osArch': platform.machine(),
        'pythonVersion': platform.python_version(),
        'cpuName': None,
        'cpuCores': None,
        'cpuThreads': None,
        'gpuNames': [],
        'totalMemGB': None,
        'bootTime': None
    }
    gpu_mem = {}

    if HAS_PSUTIL:
        info['cpuCores'] = psutil.cpu_count(logical=False)
        info['cpuThreads'] = psutil.cpu_count(logical=True)
        info['totalMemGB'] = round(psutil.virtual_memory().total / 1024 ** 3, 1)
        try:
            info['bootTime'] = time.strftime(
                '%Y-%m-%d %H:%M', time.localtime(psutil.boot_time()))
        except Exception:
            pass

    if IS_WINDOWS:
        cpu = shell.wmic_kv('wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors /value')
        if cpu.get('Name'):
            info['cpuName'] = cpu['Name']
        if not info['cpuCores'] and cpu.get('NumberOfCores'):
            info['cpuCores'] = int(cpu['NumberOfCores'])
        if not info['cpuThreads'] and cpu.get('NumberOfLogicalProcessors'):
            info['cpuThreads'] = int(cpu['NumberOfLogicalProcessors'])

        if not info['totalMemGB']:
            cs = shell.wmic_kv('wmic ComputerSystem get TotalPhysicalMemory /value')
            if cs.get('TotalPhysicalMemory'):
                info['totalMemGB'] = round(int(cs['TotalPhysicalMemory']) / 1024 ** 3, 1)

        if not info['bootTime']:
            os_ = shell.wmic_kv('wmic OS get LastBootUpTime /value')
            raw = os_.get('LastBootUpTime')
            if raw and len(raw) >= 12:
                try:
                    info['bootTime'] = (
                        f'{raw[0:4]}-{raw[4:6]}-{raw[6:8]} '
                        f'{raw[8:10]}:{raw[10:12]}')
                except Exception:
                    pass

        # wmic 已被新版 Windows 移除时，走 PowerShell Get-CimInstance 回退
        if not info['cpuName'] or not info['gpuNames']:
            ps = shell.powershell_static_kv()
            if ps:
                if not info['cpuName'] and ps.get('CPUName'):
                    info['cpuName'] = ps['CPUName']
                if not info['cpuCores'] and ps.get('Cores'):
                    try:
                        info['cpuCores'] = int(ps['Cores'])
                    except ValueError:
                        pass
                if not info['cpuThreads'] and ps.get('Threads'):
                    try:
                        info['cpuThreads'] = int(ps['Threads'])
                    except ValueError:
                        pass
                if not info['totalMemGB'] and ps.get('TotalMem'):
                    try:
                        info['totalMemGB'] = round(int(ps['TotalMem']) / 1024 ** 3, 1)
                    except ValueError:
                        pass
                if not info['bootTime'] and ps.get('Boot'):
                    info['bootTime'] = ps['Boot']
                for name, ram in ps.get('gpus', []):
                    if name and name not in info['gpuNames']:
                        info['gpuNames'].append(name)
                        try:
                            ram_v = int(ram) if ram else 0
                        except ValueError:
                            ram_v = 0
                        if ram_v <= 0:
                            ram_v = 0xFFFFFFFF
                        gpu_mem[name] = round(ram_v / 1024 ** 3, 1)

    # GPU 名称与显存总量（NVML 优先，其次 WMI，最后 wmic/PowerShell）
    if HAS_NVML:
        try:
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode('utf-8', errors='replace')
                info['gpuNames'].append(name)
                try:
                    gpu_mem[name] = round(
                        pynvml.nvmlDeviceGetMemoryInfo(h).total / 1024 ** 3, 1)
                except Exception:
                    pass
        except Exception:
            pass
    elif HAS_WMI and WMI_CLIENT:
        try:
            for a in WMI_CLIENT.query('Win32_VideoController'):
                name = getattr(a, 'Name', None)
                if name:
                    info['gpuNames'].append(name)
                    ram = getattr(a, 'AdapterRAM', 0) or 0
                    if ram <= 0:
                        ram = 0xFFFFFFFF  # WMI 32 位溢出，>4GB 时不准
                    gpu_mem[name] = round(ram / 1024 ** 3, 1)
        except Exception:
            pass
    if not info['gpuNames'] and IS_WINDOWS:
        out = shell.run('wmic path win32_VideoController get Name,AdapterRAM /value')
        if out:
            cur = {}
            for line in out.splitlines() + ['']:
                line = line.strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    cur[k.strip()] = v.strip()
                elif cur.get('Name'):
                    name = cur['Name']
                    info['gpuNames'].append(name)
                    try:
                        ram = int(cur.get('AdapterRAM') or 0)
                        if ram <= 0:
                            ram = 0xFFFFFFFF
                        gpu_mem[name] = round(ram / 1024 ** 3, 1)
                    except ValueError:
                        pass
                cur = {}

    info['gpuMemGB'] = gpu_mem
    return info


def init():
    """执行采集并写入模块缓存"""
    global _STATIC
    _STATIC = collect()
    return _STATIC


def get() -> dict:
    """读取缓存的静态信息"""
    return _STATIC


def sysinfo_payload() -> dict:
    """构造上报给前端的 sysinfo 数据（剔除空值）"""
    info = dict(_STATIC)
    info['gpuName'] = (info.get('gpuNames') or [None])[0]
    info.pop('gpuNames', None)
    return {k: v for k, v in info.items() if v is not None}
