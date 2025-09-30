"""主题管理与系统配色检测。"""
from __future__ import annotations

from dataclasses import replace
from enum import Enum
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from .constants import DARK_THEME_COLORS, LIGHT_THEME_COLORS, ThemeColors


class ThemeMode(str, Enum):
    """系统主题模式。"""

    LIGHT = "light"
    DARK = "dark"


class ThemeManager(QObject):
    """提供当前主题配色，并监听系统主题变化。"""

    theme_changed = Signal(ThemeColors)

    def __init__(self) -> None:
        super().__init__()
        self._palette = self._select_palette(self._detect_mode())
        app = QApplication.instance()
        if app:
            hints = app.styleHints()
            color_scheme_changed = getattr(hints, "colorSchemeChanged", None)
            if hasattr(color_scheme_changed, "connect"):
                color_scheme_changed.connect(self._handle_color_scheme_changed)

    @property
    def current_palette(self) -> ThemeColors:
        """返回当前配色。"""

        return self._palette

    def _detect_mode(self) -> ThemeMode:
        app = QApplication.instance()
        if not app:
            return ThemeMode.LIGHT

        hints = app.styleHints()
        color_scheme = getattr(hints, "colorScheme", None)
        if callable(color_scheme):
            scheme = color_scheme()
            if scheme == Qt.ColorScheme.Dark:
                return ThemeMode.DARK
            if scheme == Qt.ColorScheme.Light:
                return ThemeMode.LIGHT

        palette = app.palette()
        window = palette.color(QPalette.ColorRole.Window)
        text = palette.color(QPalette.ColorRole.WindowText)
        if window.value() < text.value():
            return ThemeMode.DARK
        return ThemeMode.LIGHT

    def _select_palette(self, mode: ThemeMode) -> ThemeColors:
        if mode == ThemeMode.DARK:
            return DARK_THEME_COLORS
        return LIGHT_THEME_COLORS

    @Slot(Qt.ColorScheme)
    def _handle_color_scheme_changed(self, scheme: Qt.ColorScheme) -> None:
        mode = ThemeMode.DARK if scheme == Qt.ColorScheme.Dark else ThemeMode.LIGHT
        self._apply_mode(mode)

    def _apply_mode(self, mode: ThemeMode) -> None:
        new_palette = self._select_palette(mode)
        if new_palette == self._palette:
            return
        # dataclass 默认不可变，replace 生成副本确保信号发送的是独立对象
        self._palette = replace(new_palette)
        self.theme_changed.emit(self._palette)


_THEME_MANAGER: Optional[ThemeManager] = None


def get_theme_manager() -> ThemeManager:
    """获取全局主题管理器实例。"""

    global _THEME_MANAGER
    if _THEME_MANAGER is None:
        _THEME_MANAGER = ThemeManager()
    return _THEME_MANAGER


def get_current_palette() -> ThemeColors:
    """便捷方法，返回当前主题配色。"""

    return get_theme_manager().current_palette


__all__ = [
    "ThemeManager",
    "ThemeMode",
    "get_theme_manager",
    "get_current_palette",
]

