"""路径与文件位置管理。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


_APP_DIR_NAME = "TODOList"


def _detect_base_dir() -> Path:
    """在开发与打包环境下均可用的基础目录。"""

    if getattr(sys, "frozen", False):  # PyInstaller 打包场景
        bundle_path = getattr(sys, "_MEIPASS", None)
        if bundle_path:
            return Path(bundle_path)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _detect_storage_root(base_dir: Path) -> Path:
    """确定持久化数据目录。"""

    if getattr(sys, "frozen", False):
        roaming_dir = os.getenv("APPDATA")
        if roaming_dir:
            return Path(roaming_dir) / _APP_DIR_NAME
        return Path.home() / f".{_APP_DIR_NAME.lower()}"
    return base_dir


BASE_DIR = _detect_base_dir()
RUNTIME_STORAGE_DIR = _detect_storage_root(BASE_DIR)
RUNTIME_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = RUNTIME_STORAGE_DIR / "todos.json"


def resource_path(relative_path: os.PathLike[str] | str) -> Path:
    """将相对资源路径解析为当前运行环境下的绝对路径。"""

    candidate = Path(relative_path)
    if candidate.is_absolute():
        return candidate
    return BASE_DIR / candidate


__all__ = ["BASE_DIR", "DATA_FILE", "RUNTIME_STORAGE_DIR", "resource_path"]
