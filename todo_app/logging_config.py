"""应用文件轮转日志配置。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import RUNTIME_STORAGE_DIR


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def configure_logging(storage_dir: Path | None = None) -> Path | None:
    """为 todo_app 命名空间配置幂等的文件轮转日志。"""

    target_dir = (storage_dir or RUNTIME_STORAGE_DIR) / "logs"
    log_file = target_dir / "todolist.log"
    package_logger = logging.getLogger("todo_app")
    if package_logger.level == logging.NOTSET:
        package_logger.setLevel(logging.INFO)

    for existing in package_logger.handlers:
        if isinstance(existing, RotatingFileHandler) and Path(existing.baseFilename) == log_file:
            return log_file

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=1_048_576,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError:
        return None

    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    package_logger.addHandler(handler)
    return log_file


__all__ = ["configure_logging"]
