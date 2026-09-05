#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python 后端服务入口（由 Electron 主进程启动）

实际逻辑位于 monitor 包：
  monitor/service.py    主循环（sysinfo + metrics 周期上报）
  monitor/protocol.py   stdout JSON 行协议（__PROTOCOL__ 前缀）
  monitor/deps.py       可选依赖探测（psutil/pynvml/wmi/win32pdh，全部优雅降级）
  monitor/shell.py      wmic/PowerShell 零依赖回退工具
  monitor/static_info.py静态信息采集与缓存
  monitor/cpu.py        CPU 指标
  monitor/memory.py     内存指标
  monitor/disks.py      磁盘指标
  monitor/gpu.py        GPU 指标（NVML -> PDH -> PowerShell 三级降级）
"""

import logging
import os
import sys

# 确保以任意工作目录启动时都能导入 monitor 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)

from monitor import service  # noqa: E402


if __name__ == '__main__':
    print(f'[INFO] Python 版本: {sys.version.split()[0]}', flush=True)
    service.run()
