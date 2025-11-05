"""常用工具函数。"""
from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QUrl, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import QApplication

from .constants import DEFAULT_ICON_SIZE
from .paths import resource_path
from .theme import get_current_palette

_warned_icon_paths: set[str] = set()
_warned_sound_paths: set[str] = set()


@lru_cache(maxsize=None)
def _get_font_metrics(font: QFont) -> QFontMetrics:
    """缓存 QFontMetrics，避免重复计算。"""
    return QFontMetrics(font)


def get_icon(icon_path: os.PathLike[str] | str, fallback_char: str = "●", size: QSize | None = None) -> QIcon:
    """加载图标，若缺失则生成回退图标。"""
    icon_size = size or DEFAULT_ICON_SIZE
    resolved_path: Path | None = None
    if icon_path:
        resolved_path = resource_path(icon_path)

    if resolved_path and resolved_path.exists():
        return QIcon(str(resolved_path))

    pixmap = QPixmap(icon_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setPen(QColor(get_current_palette().text_secondary))
    font = QFont()
    font.setPointSize(max(8, int(icon_size.height() * 0.7)))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, fallback_char)
    painter.end()

    if icon_path and str(icon_path) not in _warned_icon_paths:
        print(f"警告: 图标 '{icon_path}' 未找到，使用后备字符图标 '{fallback_char}'。")
        _warned_icon_paths.add(str(icon_path))
    return QIcon(pixmap)


def play_sound_effect(
    sound_effect_player: QSoundEffect,
    sound_path: os.PathLike[str] | str,
    fallback_beep: bool = True,
) -> None:
    """播放声音资源，不存在时使用系统提示音。"""
    resolved_path: Path | None = None
    if sound_path:
        resolved_path = resource_path(sound_path)

    if resolved_path and resolved_path.exists():
        sound_effect_player.setSource(QUrl.fromLocalFile(str(resolved_path)))
        sound_effect_player.play()
        return

    if sound_path and str(sound_path) not in _warned_sound_paths:
        print(f"警告: 声音文件 '{sound_path}' 未找到。将尝试使用系统提示音。")
        _warned_sound_paths.add(str(sound_path))

    if not fallback_beep:
        return

    app_instance = QApplication.instance()
    if app_instance:
        app_instance.beep()
    else:
        print("警告: QApplication 实例未找到，无法播放后备系统提示音。")


def truncate_text_for_width(text: str, font: QFont, max_width: int, min_chars: int = 6) -> str:
    """根据宽度截断文本，确保至少展示 min_chars 个字符。"""
    if not text:
        return text

    font_metrics = _get_font_metrics(font)

    if font_metrics.horizontalAdvance(text) <= max_width:
        return text

    if len(text) <= min_chars:
        return text

    ellipsis = "…"
    ellipsis_width = font_metrics.horizontalAdvance(ellipsis)
    available_width = max_width - ellipsis_width

    min_text = text[:min_chars]
    min_width = font_metrics.horizontalAdvance(min_text)
    if available_width < min_width:
        return min_text + ellipsis

    left, right = min_chars, len(text)
    best_length = min_chars

    while left <= right:
        mid = (left + right) // 2
        test_text = text[:mid]
        test_width = font_metrics.horizontalAdvance(test_text)

        if test_width <= available_width:
            best_length = mid
            left = mid + 1
        else:
            right = mid - 1

    return text[:best_length] + ellipsis


def any_true(values: Iterable[bool]) -> bool:
    """判断序列中是否存在 True。"""
    return any(values)


__all__ = [
    "get_icon",
    "play_sound_effect",
    "truncate_text_for_width",
    "any_true",
]
