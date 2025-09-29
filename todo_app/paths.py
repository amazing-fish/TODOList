"""路径与文件位置管理。"""
from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "todos.json"

__all__ = ["BASE_DIR", "DATA_FILE"]
