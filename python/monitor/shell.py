# -*- coding: utf-8 -*-
"""
子进程 shell 工具：wmic / PowerShell 零依赖回退
（嵌入式 Python 无 C 扩展时，通过系统自带命令采集）
"""

import base64
import subprocess

from .deps import IS_WINDOWS

# 隐藏子进程控制台窗口
_CREATIONFLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if IS_WINDOWS else 0


def run(cmd: str, timeout: float = 6.0):
    """执行命令并返回 stdout 文本，失败返回 None"""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, creationflags=_CREATIONFLAGS,
            errors='ignore'
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    except Exception:
        pass
    return None


def run_powershell(script: str, timeout: float = 12.0):
    """以 -EncodedCommand 方式执行 PowerShell 脚本（规避引号/换行转义问题）"""
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    return run(f'powershell -NoProfile -NonInteractive -EncodedCommand {encoded}',
               timeout=timeout)


def wmic_kv(cmd: str) -> dict:
    """
    解析 `wmic ... get a,b /value` 输出为 {key: value}
    例：Name=Intel CPU / NumberOfCores=6
    注意：新版 Windows 已移除 wmic，失败时返回空 dict
    """
    out = run(cmd)
    result = {}
    if not out:
        return result
    for line in out.splitlines():
        line = line.strip()
        if '=' in line:
            k, v = line.split('=', 1)
            if v.strip():
                result[k.strip()] = v.strip()
    return result


# PowerShell 静态信息脚本（wmic 被移除时的回退，使用系统自带 Get-CimInstance）
_PS_STATIC_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$p=Get-CimInstance Win32_Processor | Select-Object -First 1;"
    "if($p){Write-Output ('CPUName='+$p.Name);"
    "Write-Output ('Cores='+$p.NumberOfCores);"
    "Write-Output ('Threads='+$p.NumberOfLogicalProcessors)};"
    "$c=Get-CimInstance Win32_ComputerSystem | Select-Object -First 1;"
    "if($c){Write-Output ('TotalMem='+$c.TotalPhysicalMemory)};"
    "$o=Get-CimInstance Win32_OperatingSystem | Select-Object -First 1;"
    "if($o){Write-Output ('Boot='+$o.LastBootUpTime.ToString('yyyy-MM-dd HH:mm'))};"
    "Get-CimInstance Win32_VideoController | ForEach-Object {"
    "Write-Output ('GPU='+$_.Name+'@'+$_.AdapterRAM)}"
)


def powershell_static_kv() -> dict:
    """通过 PowerShell Get-CimInstance 采集静态信息（零依赖）"""
    out = run_powershell(_PS_STATIC_SCRIPT, timeout=15.0)
    result = {'gpus': []}
    if not out:
        return {}
    for line in out.splitlines():
        line = line.strip()
        if not line or '=' not in line:
            continue
        k, v = line.split('=', 1)
        v = v.strip()
        if not v:
            continue
        if k == 'GPU':
            name, _, ram = v.partition('@')
            result['gpus'].append((name.strip(), ram.strip()))
        else:
            result[k] = v
    return result


def classify_vendor(name: str) -> str:
    """根据显卡名称识别厂商"""
    low = (name or '').lower()
    if any(k in low for k in ('nvidia', 'geforce', 'quadro', 'rtx', 'gtx')):
        return 'NVIDIA'
    if any(k in low for k in ('radeon', 'amd', 'ati ')):
        return 'AMD'
    if 'intel' in low:
        return 'Intel'
    return 'Other'
