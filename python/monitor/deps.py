# -*- coding: utf-8 -*-
"""
可选依赖探测（全部优雅降级，缺失不报错）

采集策略优先级：
  1. psutil（完整依赖时优先）
  2. pynvml（NVIDIA GPU 精确数据）
  3. wmi + pywin32/PDH（Windows 下 AMD/Intel GPU）
  4. 零依赖回退：subprocess 调用系统自带 wmic / PowerShell
"""

import platform

IS_WINDOWS = platform.system() == 'Windows'

# ---------- psutil ----------
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

# ---------- pynvml（NVIDIA GPU） ----------
try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
except Exception:
    pynvml = None
    HAS_NVML = False

# ---------- wmi + pywin32（Windows 下 AMD/Intel 显卡） ----------
HAS_WMI = False
WMI_CLIENT = None
HAS_PDH = False
if IS_WINDOWS:
    try:
        import wmi
        WMI_CLIENT = wmi.WMI(namespace='root/cimv2')
        HAS_WMI = True
    except Exception:
        HAS_WMI = False
    try:
        import win32pdh  # noqa: F401
        HAS_PDH = True
    except Exception:
        HAS_PDH = False


def shutdown():
    """释放依赖资源（进程退出前调用）"""
    if HAS_NVML and pynvml is not None:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def describe() -> str:
    """依赖可用性摘要（用于启动日志）"""
    return (f'psutil: {"可用" if HAS_PSUTIL else "缺失"} | '
            f'pynvml: {"可用" if HAS_NVML else "缺失"} | '
            f'wmi: {"可用" if HAS_WMI else "缺失"} | '
            f'win32pdh: {"可用" if HAS_PDH else "缺失"}')
