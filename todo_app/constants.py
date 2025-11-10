"""应用程序常量定义。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize

from .paths import DATA_FILE


@dataclass(frozen=True)
class ThemeColors:
    """主题配色方案定义。"""

    background: str
    primary_item_bg: str
    completed_item_bg: str
    text_primary: str
    text_secondary: str
    text_completed: str
    accent: str
    accent_hover: str
    priority_high: str
    priority_medium: str
    priority_low: str
    due_warning: str
    due_critical: str
    list_label: str
    card_border: str
    action_hover_bg: str
    snooze_badge: str
    timer_positive: str
    input_background: str
    input_border: str
    secondary_background: str
    inverse_text: str


# --- 基本信息 ---
APP_NAME = "桌面待办事项 v1"
APP_VERSION = "1.7.1"

# --- 文件资源 ---
APP_ICON_PATH = "assets/icons/app_icon.svg"
TRAY_ICON_PATH = "assets/icons/tray_icon.svg"
DONE_ICON_PATH = "assets/icons/done_icon.svg"
INCOMPLETE_ICON_PATH = "assets/icons/incomplete_icon.svg"
EDIT_ICON_PATH = "assets/icons/edit_icon.svg"
DELETE_ICON_PATH = "assets/icons/delete_icon.svg"
SNOOZE_ICON_PATH = "assets/icons/snooze_icon.svg"
CALENDAR_ICON_PATH = "assets/icons/calendar_icon.svg"
ADD_ICON_PATH = "assets/icons/add_icon.svg"
REMINDER_SOUND_PATH = "reminder.wav"
DUE_SOUND_PATH = "due.wav"

# --- 颜色 ---
LIGHT_THEME_COLORS = ThemeColors(
    background="#ECEFF1",
    primary_item_bg="#FFFFFF",
    completed_item_bg="#E0E0E0",
    text_primary="#263238",
    text_secondary="#546E7A",
    text_completed="#78909C",
    accent="#00796B",
    accent_hover="#004D40",
    priority_high="#E53935",
    priority_medium="#FFB300",
    priority_low="#42A5F5",
    due_warning="#EF6C00",
    due_critical="#D32F2F",
    list_label="#1A237E",
    card_border="#CFD8DC",
    action_hover_bg="#B0BEC5",
    snooze_badge="#FF9800",
    timer_positive="#2E7D32",
    input_background="#FFFFFF",
    input_border="#B0BEC5",
    secondary_background="#FAFAFA",
    inverse_text="#FFFFFF",
)

DARK_THEME_COLORS = ThemeColors(
    background="#121212",
    primary_item_bg="#1E1E1E",
    completed_item_bg="#2A2A2A",
    text_primary="#ECEFF1",
    text_secondary="#B0BEC5",
    text_completed="#90A4AE",
    accent="#26A69A",
    accent_hover="#1E857B",
    priority_high="#EF5350",
    priority_medium="#FFCA28",
    priority_low="#64B5F6",
    due_warning="#FFB74D",
    due_critical="#FF7043",
    list_label="#90CAF9",
    card_border="#37474F",
    action_hover_bg="#455A64",
    snooze_badge="#FFB74D",
    timer_positive="#81C784",
    input_background="#263238",
    input_border="#455A64",
    secondary_background="#37474F",
    inverse_text="#121212",
)

# 默认导出的颜色常量（向后兼容，默认使用浅色主题数值）
COLOR_BACKGROUND = LIGHT_THEME_COLORS.background
COLOR_PRIMARY_ITEM_BG = LIGHT_THEME_COLORS.primary_item_bg
COLOR_COMPLETED_ITEM_BG = LIGHT_THEME_COLORS.completed_item_bg
COLOR_TEXT_PRIMARY = LIGHT_THEME_COLORS.text_primary
COLOR_TEXT_SECONDARY = LIGHT_THEME_COLORS.text_secondary
COLOR_TEXT_COMPLETED = LIGHT_THEME_COLORS.text_completed
COLOR_ACCENT = LIGHT_THEME_COLORS.accent
COLOR_ACCENT_HOVER = LIGHT_THEME_COLORS.accent_hover
COLOR_PRIORITY_HIGH = LIGHT_THEME_COLORS.priority_high
COLOR_PRIORITY_MEDIUM = LIGHT_THEME_COLORS.priority_medium
COLOR_PRIORITY_LOW = LIGHT_THEME_COLORS.priority_low
COLOR_DUE_WARNING = LIGHT_THEME_COLORS.due_warning
COLOR_DUE_CRITICAL = LIGHT_THEME_COLORS.due_critical

# --- 提醒选项 ---
REMINDER_OPTIONS_MAP = {
    "不提醒": -1,
    "到期时": 0,
    "5分钟前": 300,
    "15分钟前": 900,
    "30分钟前": 1800,
    "1小时前": 3600,
    "1天前": 86400,
}
REMINDER_SECONDS_TO_TEXT_MAP = {v: k for k, v in REMINDER_OPTIONS_MAP.items()}

# --- 图标渲染默认尺寸 ---
DEFAULT_ICON_SIZE = QSize(16, 16)

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "APP_ICON_PATH",
    "TRAY_ICON_PATH",
    "DONE_ICON_PATH",
    "INCOMPLETE_ICON_PATH",
    "EDIT_ICON_PATH",
    "DELETE_ICON_PATH",
    "SNOOZE_ICON_PATH",
    "CALENDAR_ICON_PATH",
    "ADD_ICON_PATH",
    "REMINDER_SOUND_PATH",
    "DUE_SOUND_PATH",
    "COLOR_BACKGROUND",
    "COLOR_PRIMARY_ITEM_BG",
    "COLOR_COMPLETED_ITEM_BG",
    "COLOR_TEXT_PRIMARY",
    "COLOR_TEXT_SECONDARY",
    "COLOR_TEXT_COMPLETED",
    "COLOR_ACCENT",
    "COLOR_ACCENT_HOVER",
    "COLOR_PRIORITY_HIGH",
    "COLOR_PRIORITY_MEDIUM",
    "COLOR_PRIORITY_LOW",
    "COLOR_DUE_WARNING",
    "COLOR_DUE_CRITICAL",
    "REMINDER_OPTIONS_MAP",
    "REMINDER_SECONDS_TO_TEXT_MAP",
    "DEFAULT_ICON_SIZE",
    "DATA_FILE",
    "ThemeColors",
    "LIGHT_THEME_COLORS",
    "DARK_THEME_COLORS",
]
