# -*- coding: utf-8 -*-
"""
stdout JSON 行协议
每条输出均为单行 JSON，以 __PROTOCOL__ 前缀标记，由 Electron 主进程解析：
  {"type": "sysinfo", ...}  -> 系统静态信息（启动时上报一次）
  {"type": "metrics", ...}  -> 系统监控指标（CPU/内存/GPU/磁盘，周期上报）
  {"type": "log", ...}      -> 运行日志（级别 + 文本，实时推送）
    log payload: {"type": "log", "ts": 毫秒时间戳, "level": "debug|info|warn|error", "text": str}
"""

import json
import logging
import sys
import time

PROTOCOL_PREFIX = '__PROTOCOL__ '


def emit(payload: dict):
    """向 stdout 输出一行协议 JSON"""
    sys.stdout.write(PROTOCOL_PREFIX + json.dumps(payload, ensure_ascii=False) + '\n')
    sys.stdout.flush()


def emit_log(level: str, text: str):
    """输出一条 log 协议消息（level: debug/info/warn/error）"""
    emit({
        'type': 'log',
        'ts': int(time.time() * 1000),
        'level': level,
        'text': text,
    })


# logging 标准级别 -> 协议级别（与前端颜色样式约定一致）
_LEVEL_MAP = {
    logging.DEBUG: 'debug',
    logging.INFO: 'info',
    logging.WARNING: 'warn',
    logging.ERROR: 'error',
    logging.CRITICAL: 'error',
}


class ProtocolLogHandler(logging.Handler):
    """把 logging 记录转发为 __PROTOCOL__ log 行，供 Electron 主进程解析推送前端"""

    def emit(self, record: logging.LogRecord):
        try:
            level = _LEVEL_MAP.get(record.levelno, 'info')
            text = record.getMessage()
            # 异常堆栈附加到文本尾部
            if record.exc_info:
                text = text + '\n' + logging.Formatter().formatException(record.exc_info)
            emit_log(level, text)
        except Exception:
            self.handleError(record)
