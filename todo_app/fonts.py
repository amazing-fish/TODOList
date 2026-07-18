"""应用字体注册与安全回退。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from .constants import APP_FONT_FAMILY, APP_FONT_PATH
from .paths import resource_path


def register_application_font(font_path: Path) -> str | None:
    """注册字体资源并返回 Qt 识别到的字体族。"""

    if not font_path.is_file():
        return None

    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        return None

    families = QFontDatabase.applicationFontFamilies(font_id)
    if APP_FONT_FAMILY in families:
        return APP_FONT_FAMILY
    return families[0] if families else None


def apply_application_font(font_path: Path | None = None) -> str:
    """在创建界面前应用内置字体，失败时退回系统 UI 字体。"""

    resolved_path = font_path or resource_path(APP_FONT_PATH)
    family = register_application_font(resolved_path)
    if family is None:
        system_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        family = system_font.family() or QApplication.font().family()
        print(f"警告: 字体 '{resolved_path}' 注册失败，使用系统字体 '{family}'。")

    QApplication.setFont(QFont(family, 10))
    return family


__all__ = ["apply_application_font", "register_application_font"]
