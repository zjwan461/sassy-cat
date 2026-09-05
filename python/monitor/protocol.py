# -*- coding: utf-8 -*-
"""
stdout JSON 行协议
每条输出均为单行 JSON，以 __PROTOCOL__ 前缀标记，由 Electron 主进程解析：
  {"type": "sysinfo", ...}  -> 系统静态信息（启动时上报一次）
  {"type": "metrics", ...}  -> 系统监控指标（CPU/内存/GPU/磁盘，周期上报）
"""

import json
import sys

PROTOCOL_PREFIX = '__PROTOCOL__ '


def emit(payload: dict):
    """向 stdout 输出一行协议 JSON"""
    sys.stdout.write(PROTOCOL_PREFIX + json.dumps(payload, ensure_ascii=False) + '\n')
    sys.stdout.flush()
