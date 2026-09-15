# -*- coding: utf-8 -*-
"""
静态信息采集（启动时采集一次并缓存）：
CPU 名称/核数、GPU 名称与显存总量、内存总量、启动时间等。
采集链：psutil -> wmic -> PowerShell Get-CimInstance；GPU 名称另走 NVML -> WMI -> wmic。
"""

import shutil
import socket
import platform
import time

from . import shell
from .deps import IS_WINDOWS, HAS_PSUTIL, psutil, HAS_NVML, pynvml, HAS_WMI, WMI_CLIENT

# 模块级缓存
_STATIC = {}
_SOFTWARE = {}


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


def _extract_version(text: str, index: int = 2) -> str | None:
    """从命令输出中提取版本号（按空格分割后取指定位置的 token）"""
    parts = text.strip().split()
    if len(parts) > index:
        return parts[index].rstrip(',')
    return None


def collect_software() -> dict:
    """检测当前系统安装的开发软件版本及可执行文件绝对路径。

    返回格式::

        {
            'git':    {'version': '2.43.0', 'path': 'C:\\\\Program Files\\\\Git\\\\cmd\\\\git.exe'},
            'java':   {'version': '17.0.2', 'path': 'C:\\\\Program Files\\\\Java\\\\...'},
            ...
        }

    仅包含已安装的软件；未安装的不出现。
    """
    software = {}

    # 定义检测项：(key, executable, version_args, version_parser)
    #   version_parser: callable(stdout) -> str | None
    #   当 version_args 为空字符串时，仅检测路径不获取版本
    def _parse_git(out):
        return _extract_version(out, 2)

    def _parse_java(out):
        for line in out.splitlines():
            line = line.strip()
            if 'version' in line.lower():
                for part in line.split():
                    part = part.strip('"')
                    if part and part[0].isdigit():
                        return part
        return None

    def _parse_node(out):
        return out.strip()

    def _parse_go(out):
        return _extract_version(out, 2)

    def _parse_rust(out):
        return _extract_version(out, 1)

    def _parse_docker(out):
        return _extract_version(out, 2)

    def _parse_gcc(out):
        for line in out.splitlines():
            line = line.strip()
            if line:
                for part in line.split():
                    if part and part[0].isdigit():
                        return part
        return None

    def _parse_cmake(out):
        return _extract_version(out, 2)

    def _parse_code(out):
        lines = out.strip().splitlines()
        return lines[0].strip() if lines else None

    def _parse_python(out):
        return _extract_version(out, 1)

    checks = [
        ('git',     'git',    '--version', _parse_git),
        ('java',    'java',   '-version',  _parse_java),
        ('nodejs',  'node',   '--version', _parse_node),
        ('go',      'go',     'version',   _parse_go),
        ('rust',    'rustc',  '--version', _parse_rust),
        ('docker',  'docker', '--version', _parse_docker),
        ('gcc',     'gcc',    '--version', _parse_gcc),
        ('cmake',   'cmake',  '--version', _parse_cmake),
        ('vscode',  'code',   '--version', _parse_code),
        ('python',  'python', '--version', _parse_python),
    ]

    for key, exe, args, parser in checks:
        exe_path = shutil.which(exe)
        if not exe_path:
            continue
        entry = {'path': exe_path}
        try:
            out = shell.run(f'{exe} {args}')
            if out:
                ver = parser(out)
                if ver:
                    entry['version'] = ver
        except Exception:
            pass
        software[key] = entry

    return software


def init():
    """执行采集并写入模块缓存"""
    global _STATIC, _SOFTWARE
    _STATIC = collect()
    _SOFTWARE = collect_software()
    return _STATIC


def get() -> dict:
    """读取缓存的静态信息"""
    return _STATIC


def get_software() -> dict:
    """读取缓存的开发软件信息"""
    return _SOFTWARE


def sysinfo_payload() -> dict:
    """构造上报给前端的 sysinfo 数据（剔除空值）"""
    info = dict(_STATIC)
    info['gpuName'] = (info.get('gpuNames') or [None])[0]
    info.pop('gpuNames', None)
    return {k: v for k, v in info.items() if v is not None}
