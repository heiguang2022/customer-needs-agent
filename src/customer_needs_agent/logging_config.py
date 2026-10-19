"""结构化、可轮转且不记录密钥的日志配置。"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """输出便于检索的 JSON Lines。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("conversation_id", "duration_ms", "status", "error_code", "tool_name"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str, log_file: str) -> None:
    """配置控制台与文件日志；重复调用不会重复添加处理器。"""

    global _CONFIGURED
    root = logging.getLogger()
    if _CONFIGURED:
        return
    root.setLevel(level.upper())
    formatter = JsonFormatter()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    rotating = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    rotating.setFormatter(formatter)
    root.addHandler(rotating)
    _CONFIGURED = True
