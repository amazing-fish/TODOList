"""主窗口实现。"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional
from textwrap import dedent

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QPointF,
    QRect,
    QSettings,
    QTimer,
    QUrl,
    Qt,
    QSize,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    APP_ICON_PATH,
    APP_NAME,
    APP_VERSION,
    DUE_SOUND_PATH,
    REMINDER_SECONDS_TO_TEXT_MAP,
    REMINDER_SOUND_PATH,
    SETTINGS_APPLICATION,
    SETTINGS_ORGANIZATION,
    TASK_CARD_LIST_GAP,
)
from .autostart import (
    is_autostart_enabled,
    is_autostart_supported,
    set_autostart_enabled,
)
from .dialogs import NotificationDialog, TaskEditDialog
from .layout import calculate_card_width
from .scheduling import (
    build_edit_update_fields,
    build_recurrence_completion_fields,
    build_snooze_update_fields,
    normalize_recurrence,
)
from .scrolling import SmoothScrollListWidget
from .settings_dialog import SettingsDialog
from . import storage as _storage
from .storage import (
    StorageStatus,
    get_last_load_status,
    get_last_save_status,
    load_todos,
    normalize_todo_list,
    quarantine_damaged_main_file,
    save_todos,
)
from .utils import get_icon, play_sound_effect
from .widgets import TodoItemWidget, UndoToastBar
from .theme import ThemeColors, ThemePreference, get_theme_manager


_MAIN_CONTENT_MARGIN = 15
_LIST_SCROLLBAR_WIDTH = 8
_LIST_RIGHT_MARGIN = _MAIN_CONTENT_MARGIN - _LIST_SCROLLBAR_WIDTH
_SORT_COMBO_MIN_WIDTH = 76


class _ResponsiveComboBox(QComboBox):
    """在窄布局中省略当前文本，并绘制可辨识的主题箭头。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._arrow_color = "#000000"
        self._disabled_arrow_color = "#808080"

    def set_arrow_colors(self, normal: str, disabled: str) -> None:
        self._arrow_color = normal
        self._disabled_arrow_color = disabled
        self.update()

    def initStyleOption(self, option: QStyleOptionComboBox) -> None:  # noqa: N802
        super().initStyleOption(option)
        edit_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        option.currentText = option.fontMetrics.elidedText(
            option.currentText,
            Qt.TextElideMode.ElideRight,
            max(edit_rect.width(), 0),
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        size_hint = super().minimumSizeHint()
        return QSize(self.minimumWidth(), size_hint.height())

    def unelided_items_width(self) -> int:
        """按当前字体与样式计算所有选项完整显示所需的最小宽度。"""

        if self.count() == 0:
            return self.sizeHint().width()

        text_width = max(
            self.fontMetrics().horizontalAdvance(self.itemText(index))
            for index in range(self.count())
        )
        option = QStyleOptionComboBox()
        QComboBox.initStyleOption(self, option)
        height = max(self.sizeHint().height(), 1)

        for candidate_width in range(text_width, text_width + 128):
            option.rect = QRect(0, 0, candidate_width, height)
            edit_rect = self.style().subControlRect(
                QStyle.ComplexControl.CC_ComboBox,
                option,
                QStyle.SubControl.SC_ComboBoxEditField,
                self,
            )
            arrow_rect = self.style().subControlRect(
                QStyle.ComplexControl.CC_ComboBox,
                option,
                QStyle.SubControl.SC_ComboBoxArrow,
                self,
            )
            if (
                edit_rect.width() >= text_width
                and arrow_rect.left() >= edit_rect.right()
                and arrow_rect.right() < candidate_width
            ):
                return candidate_width

        return text_width + 127

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

        arrow_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxArrow,
            self,
        )
        arrow_color = (
            self._arrow_color
            if self.isEnabled()
            else self._disabled_arrow_color
        )
        pen = QPen(QColor(arrow_color), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        center = arrow_rect.center()
        painter.drawLine(
            QPointF(center.x() - 4, center.y() - 2),
            QPointF(center.x(), center.y() + 2),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() + 2),
            QPointF(center.x() + 4, center.y() - 2),
        )
        painter.end()


class ModernTodoAppWindow(QMainWindow):
    """现代风格的待办事项管理主窗口。"""

    def __init__(self):
        super().__init__()
        self.todos: List[Dict] = load_todos()
        self._load_storage_status: Optional[StorageStatus] = (
            get_last_load_status() if load_todos is _storage.load_todos else None
        )
        self._storage_status: Optional[StorageStatus] = self._load_storage_status
        self._notification_dialog: Optional[NotificationDialog] = None
        self.settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        self._quitting_app = False
        self._restoring_view_options = False

        self.theme_manager = get_theme_manager()
        self._palette: ThemeColors = self.theme_manager.current_palette
        self.theme_manager.theme_changed.connect(self._on_theme_changed)

        self.reminder_sound = QSoundEffect(self)
        self.due_sound = QSoundEffect(self)
        self.reminder_sound.setVolume(0.7)
        self.due_sound.setVolume(0.8)

        self._task_edit_dialog: Optional[TaskEditDialog] = None
        self._settings_dialog: Optional[SettingsDialog] = None
        self._deferred_undo_toast: Optional[tuple[str, object]] = None
        self._schedule_revisions: dict[int, int] = {}
        self._always_on_top = False
        self._sound_enabled = True
        self._dnd_enabled = False
        self._dnd_until_utc: Optional[datetime] = None
        self._pending_dnd_restore = False
        self._empty_placeholder_item: Optional[QListWidgetItem] = None
        self._empty_placeholder_widget: Optional[QWidget] = None
        self._empty_placeholder_label: Optional[QLabel] = None
        self._empty_reset_button: Optional[QPushButton] = None
        self._todo_items_by_id: dict[int, QListWidgetItem] = {}
        self._todo_widgets_by_id: dict[int, TodoItemWidget] = {}
        self._reconciling_todo_list = False
        self._syncing_todo_card_sizes = False

        self._build_ui()
        self._bind_shortcuts()
        self._create_tray_icon()
        self.restore_geometry_and_state()
        self.update_list_widget()
        self._sync_storage_warning_banner()

        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.tick_update)
        self.master_timer.start(1000)

        self._on_top_restore_timer = QTimer(self)
        self._on_top_restore_timer.setSingleShot(True)
        self._on_top_restore_timer.timeout.connect(self._restore_window_stays_on_top_flag)

    # --- UI 初始化 ---
    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} - v{APP_VERSION}")
        self.setWindowIcon(get_icon(APP_ICON_PATH, "T"))
        self.setMinimumSize(320, 560)
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(
            _MAIN_CONTENT_MARGIN,
            _MAIN_CONTENT_MARGIN,
            _LIST_RIGHT_MARGIN,
            _MAIN_CONTENT_MARGIN,
        )
        main_layout.setSpacing(12)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, _LIST_SCROLLBAR_WIDTH, 0)
        controls_layout.setSpacing(10)

        self.filter_label = QLabel("筛选:")
        controls_layout.addWidget(self.filter_label)
        self.filter_combo = _ResponsiveComboBox()
        self.filter_combo.addItems(["全部", "未完成", "今天到期", "已逾期", "高优先级", "已完成"])
        self.filter_combo.currentTextChanged.connect(self._on_view_option_changed)
        controls_layout.addWidget(self.filter_combo)

        self.sort_label = QLabel("排序:")
        controls_layout.addWidget(self.sort_label)
        self.sort_combo = _ResponsiveComboBox()
        self.sort_combo.addItems(
            ["创建时间 (新->旧)", "创建时间 (旧->新)", "截止日期 (近->远)", "截止日期 (远->近)", "优先级 (高->低)"]
        )
        self.sort_combo.currentTextChanged.connect(self._on_view_option_changed)
        controls_layout.addWidget(self.sort_combo)

        controls_layout.addStretch(1)

        self.add_button = QPushButton()
        self.add_button.setToolTip("完整新建任务 (Ctrl+Shift+N)")
        self.add_button.setFixedSize(36, 36)
        self.add_button.setIconSize(QSize(18, 18))
        self.add_button.setAccessibleName("添加任务")
        self.add_button.clicked.connect(lambda _checked=False: self.show_add_task_dialog())

        self.settings_button = QPushButton("设置")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setToolTip("打开设置与数据工具 (Ctrl+,)")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.clicked.connect(lambda _checked=False: self.open_settings_dialog())

        self.pin_button = QPushButton("置顶")
        self.pin_button.setObjectName("pinWindowButton")
        self.pin_button.setCheckable(True)
        self.pin_button.setToolTip("切换窗口始终置顶")
        self.pin_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_button.toggled.connect(self._on_pin_toggled)

        list_header_layout = QHBoxLayout()
        list_header_layout.setContentsMargins(0, 0, _LIST_SCROLLBAR_WIDTH, 0)
        list_header_layout.setSpacing(6)
        self.list_label = QLabel("待办列表")
        self.status_summary_label = QLabel()
        self.status_summary_label.setObjectName("statusSummaryLabel")
        list_header_layout.addWidget(self.list_label)
        list_header_layout.addWidget(self.status_summary_label)
        list_header_layout.addStretch(1)
        list_header_layout.addWidget(self.settings_button)
        list_header_layout.addWidget(self.pin_button)
        list_header_layout.addWidget(self.add_button)
        main_layout.addLayout(list_header_layout)

        quick_add_layout = QHBoxLayout()
        quick_add_layout.setContentsMargins(0, 0, _LIST_SCROLLBAR_WIDTH, 0)
        quick_add_layout.setSpacing(6)
        self.quick_add_input = QLineEdit()
        self.quick_add_input.setObjectName("quickAddInput")
        self.quick_add_input.setPlaceholderText("快速添加待办… Enter 直建 / Shift+Enter 详情")
        self.quick_add_input.installEventFilter(self)
        quick_add_layout.addWidget(self.quick_add_input, 1)
        main_layout.addLayout(quick_add_layout)

        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, _LIST_SCROLLBAR_WIDTH, 0)
        search_layout.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("搜索待办内容… (Ctrl+F)")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.installEventFilter(self)
        search_layout.addWidget(self.search_input, 1)
        main_layout.addLayout(search_layout)

        main_layout.addLayout(controls_layout)

        self.storage_warning_banner = QFrame()
        self.storage_warning_banner.setObjectName("storageWarningBanner")
        banner_layout = QVBoxLayout(self.storage_warning_banner)
        banner_layout.setContentsMargins(10, 8, 10, 8)
        banner_layout.setSpacing(6)
        self.storage_warning_label = QLabel()
        self.storage_warning_label.setWordWrap(True)
        banner_layout.addWidget(self.storage_warning_label)
        banner_actions = QHBoxLayout()
        banner_actions.setContentsMargins(0, 0, 0, 0)
        banner_actions.setSpacing(6)
        self.open_storage_dir_button = QPushButton("打开目录")
        self.open_storage_dir_button.setObjectName("openStorageDirButton")
        self.open_storage_dir_button.clicked.connect(self._open_storage_directory)
        self.recover_storage_button = QPushButton("备份并恢复可写")
        self.recover_storage_button.setObjectName("recoverStorageButton")
        self.recover_storage_button.clicked.connect(self._recover_damaged_storage)
        banner_actions.addWidget(self.open_storage_dir_button)
        banner_actions.addWidget(self.recover_storage_button)
        banner_actions.addStretch(1)
        banner_layout.addLayout(banner_actions)
        self.storage_warning_banner.setVisible(False)
        main_layout.addWidget(self.storage_warning_banner)

        self.list_widget = SmoothScrollListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # QListView::spacing 会填充每个 item 四周，相邻卡片间距因此是该值的两倍。
        self.list_widget.setSpacing(TASK_CARD_LIST_GAP // 2)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        scrollbar = self.list_widget.verticalScrollBar()
        scrollbar.setFixedWidth(_LIST_SCROLLBAR_WIDTH)
        scrollbar.rangeChanged.connect(self._sync_list_scrollbar_gutter)
        scrollbar.valueChanged.connect(lambda _value: self._refresh_visible_todo_timers())
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.viewport().installEventFilter(self)
        self._sync_list_scrollbar_gutter()
        main_layout.addWidget(self.list_widget, 1)

        self.undo_toast_bar = UndoToastBar(self, palette=self._palette)
        main_layout.addWidget(self.undo_toast_bar)
        self._apply_palette(self._palette)

    def _bind_shortcuts(self) -> None:
        self._shortcut_quick_add = QShortcut(QKeySequence("Ctrl+N"), self)
        self._shortcut_quick_add.activated.connect(self._focus_quick_add)
        self._shortcut_full_add = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        self._shortcut_full_add.activated.connect(
            lambda: self.show_add_task_dialog(initial_text=self.quick_add_input.text().strip())
        )
        self._shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self._shortcut_search.activated.connect(self._focus_search_input)
        self._shortcut_escape = QShortcut(QKeySequence("Esc"), self)
        self._shortcut_escape.activated.connect(self._handle_escape_shortcut)
        self._shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self._shortcut_undo.activated.connect(self._handle_undo_shortcut)
        self._shortcut_delete = QShortcut(QKeySequence("Delete"), self)
        self._shortcut_delete.activated.connect(self._handle_delete_shortcut)
        self._shortcut_settings = QShortcut(QKeySequence("Ctrl+,"), self)
        self._shortcut_settings.activated.connect(self.open_settings_dialog)

    def _apply_palette(self, palette: ThemeColors) -> None:
        """根据主题配色刷新窗口视觉样式。"""

        self._palette = palette
        self.setStyleSheet(f"QMainWindow {{ background-color: {palette.background}; }}")
        self.add_button.setIcon(self._build_add_icon(palette.inverse_text))
        self.add_button.setStyleSheet(
            f"""
            QPushButton {{
                 background-color: {palette.accent}; color: {palette.inverse_text};
                 border: none; border-radius: 18px; font-weight: bold; font-size: 16pt;
            }}
             QPushButton:hover {{ background-color: {palette.accent_hover}; }}
             QPushButton:pressed {{ background-color: {palette.accent_hover}; }}
             """
        )
        self.list_label.setStyleSheet(
            f"font-size: 13pt; font-weight:bold; color: {palette.list_label}; margin-top: 2px; margin-bottom: 2px;"
        )
        if hasattr(self, "status_summary_label"):
            self.status_summary_label.setStyleSheet(
                f"font-size: 9pt; color: {palette.text_secondary}; background-color: transparent;"
            )
        header_pill_button_style = f"""
            QPushButton#pinWindowButton,
            QPushButton#settingsButton {{
                background-color: {palette.action_button_bg};
                color: {palette.text_primary};
                border: 1px solid {palette.action_button_border};
                border-radius: 5px;
                padding: 4px 7px;
                font-size: 9pt;
            }}
            QPushButton#pinWindowButton:hover,
            QPushButton#settingsButton:hover {{
                border-color: {palette.accent};
            }}
            QPushButton#pinWindowButton:checked {{
                background-color: {palette.accent};
                color: {palette.inverse_text};
                border-color: {palette.accent};
            }}
        """
        if hasattr(self, "settings_button"):
            self.settings_button.setStyleSheet(header_pill_button_style)
        if hasattr(self, "pin_button"):
            self.pin_button.setStyleSheet(header_pill_button_style)
        line_edit_style = f"""
            QLineEdit {{
                background-color: {palette.input_background};
                color: {palette.text_primary};
                border: 1px solid {palette.input_border};
                border-radius: 5px;
                padding: 5px 8px;
                font-size: 9.5pt;
            }}
            QLineEdit:focus {{
                border: 1.5px solid {palette.accent};
            }}
        """
        if hasattr(self, "quick_add_input"):
            self.quick_add_input.setStyleSheet(line_edit_style)
        if hasattr(self, "search_input"):
            self.search_input.setStyleSheet(line_edit_style)
        if hasattr(self, "undo_toast_bar"):
            self.undo_toast_bar.apply_palette(palette)
        self.filter_label.setStyleSheet(
            f"color: {palette.text_primary}; font-size: 10pt; background-color: transparent;"
        )
        self.sort_label.setStyleSheet(
            f"color: {palette.text_primary}; font-size: 10pt; background-color: transparent;"
        )
        self._apply_list_palette(palette)
        self._apply_combo_palette(self.filter_combo, palette)
        self._apply_combo_palette(self.sort_combo, palette)
        if hasattr(self, "storage_warning_banner"):
            self.storage_warning_banner.setStyleSheet(
                f"""
                QFrame#storageWarningBanner {{
                    background-color: {palette.priority_high_bg};
                    border: 1px solid {palette.due_critical};
                    border-radius: 6px;
                }}
                QFrame#storageWarningBanner QLabel {{
                    color: {palette.priority_high};
                    font-size: 9pt;
                    background-color: transparent;
                }}
                QFrame#storageWarningBanner QPushButton {{
                    background-color: {palette.action_button_bg};
                    color: {palette.text_primary};
                    border: 1px solid {palette.action_button_border};
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 9pt;
                }}
                QFrame#storageWarningBanner QPushButton:hover {{
                    border-color: {palette.accent};
                }}
                """
            )
        if self._empty_placeholder_label is not None:
            self._empty_placeholder_label.setStyleSheet(
                f"color: {palette.text_secondary}; font-style: italic; font-size: 11.5pt; background-color: transparent;"
            )
        if self._empty_reset_button is not None:
            self._empty_reset_button.setStyleSheet(
                f"""
                QPushButton#resetFilterButton {{
                    background-color: {palette.action_button_bg};
                    color: {palette.accent};
                    border: 1px solid {palette.accent};
                    border-radius: 5px;
                    padding: 6px 12px;
                    font-size: 9.5pt;
                }}
                QPushButton#resetFilterButton:hover {{
                    background-color: {palette.accent};
                    color: {palette.inverse_text};
                }}
                """
            )

    def _apply_list_palette(self, palette: ThemeColors) -> None:
        """应用列表及其紧凑纵向滚动条的主题样式。"""

        self.list_widget.setStyleSheet(
            dedent(
                f"""
                QListWidget {{
                    background-color: transparent;
                    border: none;
                    padding: 0px;
                }}
                QListWidget::item {{
                    border: none;
                    margin: 0px;
                    padding: 0px;
                }}
                QScrollBar:vertical {{
                    background-color: transparent;
                    width: {_LIST_SCROLLBAR_WIDTH}px;
                    margin: 0px;
                }}
                QScrollBar::handle:vertical {{
                    background-color: {palette.input_border};
                    border-radius: 4px;
                    min-height: 28px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background-color: {palette.accent};
                }}
                QScrollBar::add-line:vertical,
                QScrollBar::sub-line:vertical {{
                    background: none;
                    border: none;
                    height: 0px;
                }}
                QScrollBar::add-page:vertical,
                QScrollBar::sub-page:vertical {{
                    background-color: transparent;
                }}
                """
            )
        )

    def _sync_list_scrollbar_gutter(
        self,
        _minimum: int = 0,
        _maximum: int = 0,
    ) -> None:
        """滚动条隐藏时保留等宽 gutter，使卡片左右外边距稳定。"""

        scrollbar = self.list_widget.verticalScrollBar()
        right_gutter = (
            0
            if scrollbar.maximum() > scrollbar.minimum()
            else _LIST_SCROLLBAR_WIDTH
        )
        margins = self.list_widget.viewportMargins()
        if margins.right() == right_gutter:
            return

        self.list_widget.setViewportMargins(
            margins.left(),
            margins.top(),
            right_gutter,
            margins.bottom(),
        )
        if not self._reconciling_todo_list:
            self._sync_todo_card_sizes()

    @staticmethod
    def _build_add_icon(color: str) -> QIcon:
        """绘制透明背景加号，圆形背景只由按钮主题样式负责。"""

        pixmap = QPixmap(QSize(18, 18))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(4.0, 9.0), QPointF(14.0, 9.0))
        painter.drawLine(QPointF(9.0, 4.0), QPointF(9.0, 14.0))
        painter.end()
        return QIcon(pixmap)

    def _apply_combo_palette(self, combo: Optional[QComboBox], palette: ThemeColors) -> None:
        """为筛选和排序下拉框应用主题色样式。"""

        if combo is None:
            return

        combo.setCursor(Qt.CursorShape.PointingHandCursor)

        combo.setStyleSheet(
            dedent(
                f"""
                QComboBox {{
                    background-color: {palette.input_background};
                    color: {palette.text_primary};
                    border: 1px solid {palette.input_border};
                    border-radius: 4px;
                    padding: 1px 14px 1px 6px;
                    min-height: 0px;
                }}
                QComboBox:focus {{
                    border-color: {palette.accent};
                }}
                QComboBox:hover {{
                    border-color: {palette.accent_hover};
                }}
                QComboBox:disabled {{
                    color: {palette.text_secondary};
                    background-color: {palette.secondary_background};
                }}
                QComboBox::drop-down {{
                    subcontrol-origin: padding;
                    subcontrol-position: center right;
                    width: 14px;
                    border: none;
                    background-color: transparent;
                }}
                QComboBox::down-arrow {{
                    image: none;
                    width: 0px;
                    height: 0px;
                }}
                QComboBox QListView,
                QComboBox QAbstractItemView {{
                    background-color: {palette.secondary_background};
                    color: {palette.text_primary};
                    border: 1px solid {palette.input_border};
                    border-radius: 4px;
                    padding: 2px 0px;
                    selection-background-color: {palette.accent};
                    selection-color: {palette.inverse_text};
                    outline: 0;
                }}
                QComboBox QListView::item,
                QComboBox QAbstractItemView::item {{
                    padding: 2px 8px;
                    margin: 0px;
                }}
                QComboBox QListView::item:hover,
                QComboBox QAbstractItemView::item:hover {{
                    background-color: {palette.accent_hover};
                    color: {palette.inverse_text};
                }}
                """
            )
        )

        if isinstance(combo, _ResponsiveComboBox):
            combo.set_arrow_colors(
                palette.text_primary,
                palette.text_secondary,
            )

        self._update_combo_compact_width(combo)

    def _update_combo_compact_width(self, combo: Optional[QComboBox]) -> None:
        """让筛选框保持紧凑，并允许排序框在最小窗口内收缩。"""

        if combo is None:
            return

        if combo.count() == 0:
            return

        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        if combo is self.filter_combo:
            combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            combo.setFixedWidth(combo.unelided_items_width())
            return

        combo.setMinimumWidth(_SORT_COMBO_MIN_WIDTH)
        combo.setMaximumWidth(16777215)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.updateGeometry()

    def _refresh_item_widgets_palette(self, palette: ThemeColors) -> None:
        """遍历所有待办卡片并刷新其配色。"""

        for index in range(self.list_widget.count()):
            list_item = self.list_widget.item(index)
            if not list_item:
                continue
            item_widget = self.list_widget.itemWidget(list_item)
            if isinstance(item_widget, TodoItemWidget):
                item_widget.apply_palette(palette)

    @Slot(ThemeColors)
    def _on_theme_changed(self, palette: ThemeColors) -> None:
        """系统主题变化后重新应用配色。"""

        self._apply_palette(palette)
        self._refresh_item_widgets_palette(palette)

    def _persist_todos(self) -> bool:
        """统一持久化任务列表，并在真实存储处于异常态时更新顶部提示横幅。"""

        saved = save_todos(self.todos)
        if save_todos is _storage.save_todos:
            status = get_last_save_status()
            self._storage_status = status
            self._sync_storage_warning_banner()
            return bool(saved)
        return True

    def _sync_storage_warning_banner(self) -> None:
        status = self._storage_status
        if status is None or status.healthy:
            self.storage_warning_banner.setVisible(False)
            self.storage_warning_label.setText("")
            return
        self.storage_warning_label.setText(status.message)
        self.recover_storage_button.setVisible(status.read_only)
        self.storage_warning_banner.setVisible(True)

    def _open_storage_directory(self) -> None:
        target_dir = (
            self._storage_status.data_file.parent
            if self._storage_status is not None
            else _storage.DATA_FILE.parent
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir)))

    def _recover_damaged_storage(self) -> None:
        status = self._storage_status
        data_file = status.data_file if status is not None else _storage.DATA_FILE
        reply = QMessageBox.question(
            self,
            "恢复可写存储",
            (
                f"将把损坏的 {data_file.name} 备份重命名为同目录下的隔离文件，"
                "并把当前已恢复的任务列表重新写入主文件。\n\n是否继续？"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            quarantine_path = quarantine_damaged_main_file(self.todos)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "恢复失败", f"隔离损坏文件或写入数据失败：{exc}")
            return
        self._storage_status = get_last_save_status()
        self._sync_storage_warning_banner()
        QMessageBox.information(
            self,
            "已恢复可写",
            f"损坏文件已保留为：{quarantine_path.name}\n当前待办数据已可正常保存。",
        )

    @Slot(str)
    def _on_view_option_changed(self, _value: str) -> None:
        if self._restoring_view_options:
            return
        self.settings.setValue("filterOption", self.filter_combo.currentText())
        self.settings.setValue("sortOption", self.sort_combo.currentText())
        self.update_list_widget()

    # --- 主循环刷新 ---
    def tick_update(self) -> None:
        now_utc = datetime.now(timezone.utc)
        was_dnd_enabled = self._dnd_enabled
        dnd_active = self.is_dnd_active(now_utc=now_utc)
        changed_ids: set[int] = set()
        notification_requests: list[tuple[dict, bool]] = []
        for original_ref in self.todos:
            snooze_until = original_ref.get("snoozeUntil")
            if snooze_until:
                try:
                    if datetime.fromisoformat(snooze_until.replace("Z", "+00:00")) <= now_utc:
                        original_ref.update(
                            {
                                "snoozeUntil": None,
                                "notifiedForReminder": False,
                                "notifiedForDue": False,
                            }
                        )
                        changed_ids.add(original_ref["id"])
                except ValueError:
                    original_ref["snoozeUntil"] = None
                    changed_ids.add(original_ref["id"])
            if dnd_active:
                continue
            notification_request = self._check_for_notification(original_ref, now_utc)
            if notification_request:
                notification_requests.append(notification_request)
                changed_ids.add(original_ref["id"])

        if changed_ids:
            self._persist_todos()
            self.update_list_widget(changed_ids=changed_ids)
        self._refresh_visible_todo_timers(current_time_utc=now_utc)
        if notification_requests and not dnd_active:
            self._show_notification_batch(notification_requests)
        elif (
            (was_dnd_enabled or self._pending_dnd_restore)
            and not dnd_active
            and self._notification_dialog is not None
            and not self._notification_dialog.isVisible()
            and self.isVisible()
            and not self.isMinimized()
        ):
            self._restore_notification_dialog()

    def _refresh_visible_todo_timers(
        self, *, current_time_utc: Optional[datetime] = None,
    ) -> None:
        """仅刷新与视口相交的卡片；数据变更仍由列表协调统一处理。"""

        if (
            self._quitting_app
            or self._reconciling_todo_list
            or self._syncing_todo_card_sizes
            or not self.list_widget.isVisible()
            or self.isMinimized()
        ):
            return
        now_utc = current_time_utc or datetime.now(timezone.utc)
        viewport_rect = self.list_widget.viewport().rect()
        for index in range(self.list_widget.count()):
            list_item = self.list_widget.item(index)
            item_rect = self.list_widget.visualItemRect(list_item)
            if item_rect.top() > viewport_rect.bottom():
                break
            if not item_rect.intersects(viewport_rect):
                continue
            item_widget = self.list_widget.itemWidget(list_item)
            if not isinstance(item_widget, TodoItemWidget):
                continue
            item_widget.update_timer_display(now_utc)

    # --- 通知逻辑 ---
    def _check_for_notification(
        self, todo: dict, current_time_utc: datetime
    ) -> Optional[tuple[dict, bool]]:
        if todo.get("completed"):
            self._remove_notification_task(todo.get("id"))
            return None

        due_date_str = todo.get("dueDate")
        if not due_date_str:
            return None

        try:
            due_date_dt = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        except ValueError:
            print(f"错误: 任务ID {todo.get('id', '未知')} 截止日期格式无效: {due_date_str}")
            return None

        snooze_until = todo.get("snoozeUntil")
        if snooze_until:
            try:
                if datetime.fromisoformat(snooze_until.replace("Z", "+00:00")) > current_time_utc:
                    return None
            except ValueError:
                pass

        reminder_offset_sec = todo.get("reminderOffset", 0)
        if reminder_offset_sec >= 0:
            reminder_time_dt = due_date_dt - timedelta(seconds=reminder_offset_sec)
            if (
                reminder_time_dt <= current_time_utc
                and due_date_dt > current_time_utc
                and not todo.get("notifiedForReminder", False)
            ):
                todo["notifiedForReminder"] = True
                todo["lastNotifiedAt"] = current_time_utc.isoformat()
                return todo, False

        if due_date_dt <= current_time_utc and not todo.get("notifiedForDue", False):
            todo["notifiedForDue"] = True
            todo["notifiedForReminder"] = True
            todo["lastNotifiedAt"] = current_time_utc.isoformat()
            return todo, True

        return None

    def _show_notification_batch(self, requests: list[tuple[dict, bool]]) -> None:
        if self.is_dnd_active():
            return
        if self._sound_enabled:
            if any(is_due for _, is_due in requests):
                play_sound_effect(self.due_sound, DUE_SOUND_PATH)
            else:
                play_sound_effect(self.reminder_sound, REMINDER_SOUND_PATH)

        dialog = self._notification_dialog
        if dialog is None:
            dialog = NotificationDialog(requests, self)
            self._notification_dialog = dialog
            dialog.complete_requested.connect(self._handle_notification_complete)
            dialog.snooze_requested.connect(self._handle_notification_snooze)
            dialog.ignore_requested.connect(self._handle_notification_ignore)
            dialog.acknowledge_requested.connect(self._handle_notification_acknowledge)
            dialog.edit_requested.connect(self._handle_notification_edit)
            dialog.open_main_window_requested.connect(self.activate_from_external_launch)
            dialog.finished.connect(self._on_notification_dialog_finished)
        else:
            dialog.add_or_update_tasks(requests)
        self._restore_notification_dialog()

    def _on_notification_dialog_finished(self, _result: int) -> None:
        if self._notification_dialog is self.sender():
            self._notification_dialog = None
            self._pending_dnd_restore = False

    def _bump_schedule_revision(self, todo_id: object) -> int:
        normalized = self._normalize_todo_id(todo_id)
        if normalized is None:
            return 0
        next_rev = self._schedule_revisions.get(normalized, 0) + 1
        self._schedule_revisions[normalized] = next_rev
        return next_rev

    def _complete_todo_in_place(
        self,
        todo: dict,
        *,
        now_utc: Optional[datetime] = None,
    ) -> tuple[bool, bool]:
        """完成待办；若配置了重复周期则自动推进到下一次截止时间。"""

        if todo.get("completed", False):
            return False, False
        recurrence_fields = build_recurrence_completion_fields(todo, now_utc=now_utc)
        if recurrence_fields is not None:
            todo.update(recurrence_fields)
            return True, True
        todo.update(
            {
                "completed": True,
                "snoozeUntil": None,
                "notifiedForReminder": True,
                "notifiedForDue": True,
            }
        )
        return True, False

    def _handle_notification_complete(self, todo_ids: list[int]) -> None:
        requested_ids = {int(todo_id) for todo_id in todo_ids}
        changed_ids: set[int] = set()
        succeeded_ids: list[int] = []
        staged_snapshots: dict[int, tuple[dict, int]] = {}
        advanced_ids: list[int] = []
        failed_errors: list[str] = []
        now_utc = datetime.now(timezone.utc)
        for todo in self.todos:
            tid = todo.get("id")
            if tid not in requested_ids or todo.get("completed", False):
                continue
            int_id = int(tid)
            pre_snapshot = copy.deepcopy(todo)
            prev_rev = self._schedule_revisions.get(int_id, 0)
            try:
                changed, advanced = self._complete_todo_in_place(todo, now_utc=now_utc)
            except (OverflowError, ValueError) as exc:
                failed_errors.append(f"「{str(todo.get('text', ''))[:16]}」无法推进下一次周期：{exc}")
                continue
            if changed:
                changed_ids.add(int_id)
                succeeded_ids.append(int_id)
                staged_snapshots[int_id] = (pre_snapshot, prev_rev)
                if advanced:
                    advanced_ids.append(int_id)

        if changed_ids:
            if not self._persist_todos():
                restored_todos: list[dict] = []
                for idx, item in enumerate(self.todos):
                    item_id = item.get("id")
                    if isinstance(item_id, int) and item_id in staged_snapshots:
                        snap, prev_rev = staged_snapshots[item_id]
                        self.todos[idx] = snap
                        self._schedule_revisions[item_id] = prev_rev
                        restored_todos.append(snap)
                if restored_todos and self._notification_dialog is not None:
                    self._notification_dialog.refresh_tasks_if_present(restored_todos)
                QMessageBox.warning(
                    self,
                    "保存失败",
                    "无法保存任务完成状态到磁盘，所有修改已回滚。",
                )
                return

            committed_revs: dict[int, tuple[dict, int]] = {}
            for int_id in succeeded_ids:
                rev = self._bump_schedule_revision(int_id)
                if int_id in staged_snapshots and int_id in advanced_ids:
                    committed_revs[int_id] = (staged_snapshots[int_id][0], rev)

            self._remove_notification_tasks(succeeded_ids)
            self.update_list_widget(changed_ids=changed_ids)

            if committed_revs and hasattr(self, "undo_toast_bar"):
                if len(committed_revs) == 1:
                    only_snap = next(iter(committed_revs.values()))[0]
                    raw_text = str(only_snap.get("text", ""))
                    preview = raw_text[:18] + ("…" if len(raw_text) > 18 else "")
                    toast_msg = f"已完成本轮「{preview}」，已安排下一次"
                else:
                    toast_msg = f"已完成本轮 {len(committed_revs)} 条重复任务，已安排下一次"

                def _undo_notification_recurrence() -> bool:
                    restored_ids: set[int] = set()
                    pre_undo_snapshots: dict[int, dict] = {}
                    for idx, item in enumerate(self.todos):
                        item_id = item.get("id")
                        if not isinstance(item_id, int) or item_id not in committed_revs:
                            continue
                        snap, expected_rev = committed_revs[item_id]
                        if self._schedule_revisions.get(item_id, 0) != expected_rev:
                            continue
                        pre_undo_snapshots[item_id] = copy.deepcopy(item)
                        item.update(
                            {
                                "completed": bool(snap.get("completed", False)),
                                "dueDate": snap.get("dueDate"),
                                "recurrence": copy.deepcopy(snap.get("recurrence")),
                                "snoozeUntil": snap.get("snoozeUntil"),
                                "notifiedForReminder": bool(snap.get("notifiedForReminder", False)),
                                "notifiedForDue": bool(snap.get("notifiedForDue", False)),
                                "lastNotifiedAt": snap.get("lastNotifiedAt"),
                            }
                        )
                        restored_ids.add(item_id)
                    if not restored_ids:
                        return True
                    if not self._persist_todos():
                        restored_live: list[dict] = []
                        for item in self.todos:
                            item_id = item.get("id")
                            if isinstance(item_id, int) and item_id in pre_undo_snapshots:
                                item.clear()
                                item.update(pre_undo_snapshots[item_id])
                                restored_live.append(item)
                        if restored_live and self._notification_dialog is not None:
                            self._notification_dialog.refresh_tasks_if_present(restored_live)
                        QMessageBox.warning(
                            self,
                            "撤销失败",
                            "无法将撤销后的任务状态写入磁盘，已保留撤销操作，请稍后重试。",
                        )
                        return False
                    for item_id in restored_ids:
                        self._bump_schedule_revision(item_id)
                    self._remove_notification_tasks(list(restored_ids))
                    self.update_list_widget(changed_ids=restored_ids)
                    return True

                self.undo_toast_bar.show_toast(toast_msg, _undo_notification_recurrence)

        if failed_errors:
            QMessageBox.warning(self, "重复任务推进失败", "\n".join(failed_errors))

    def _handle_notification_snooze(
        self, todo_ids: list[int], snooze_duration: timedelta
    ) -> None:
        requested_ids = {int(todo_id) for todo_id in todo_ids}
        changed_ids: set[int] = set()
        for todo in self.todos:
            if todo.get("id") not in requested_ids or todo.get("completed", False):
                continue
            todo.update(build_snooze_update_fields(todo, snooze_duration))
            self._bump_schedule_revision(todo["id"])
            changed_ids.add(todo["id"])

        self._remove_notification_tasks(list(requested_ids))
        if changed_ids:
            self._persist_todos()
            self.update_list_widget(changed_ids=changed_ids)

    def _handle_notification_ignore(self, todo_ids: list[int]) -> None:
        requested_ids = {int(todo_id) for todo_id in todo_ids}
        staged_snapshots: dict[int, tuple[dict, dict[str, object]]] = {}
        changed_ids: set[int] = set()
        for todo in self.todos:
            tid = todo.get("id")
            if tid not in requested_ids:
                continue
            updated_fields = {
                "dueDate": None,
                "snoozeUntil": None,
                "notifiedForReminder": False,
                "notifiedForDue": False,
            }
            if any(todo.get(key) != value for key, value in updated_fields.items()):
                snapshot_data = {
                    "dueDate": todo.get("dueDate"),
                    "snoozeUntil": todo.get("snoozeUntil"),
                    "notifiedForReminder": bool(todo.get("notifiedForReminder", False)),
                    "notifiedForDue": bool(todo.get("notifiedForDue", False)),
                }
                pre_snapshot = copy.deepcopy(todo)
                todo.update(updated_fields)
                staged_snapshots[int(tid)] = (pre_snapshot, snapshot_data)
                changed_ids.add(int(tid))

        if changed_ids:
            if not self._persist_todos():
                restored_todos: list[dict] = []
                for idx, item in enumerate(self.todos):
                    tid = item.get("id")
                    if isinstance(tid, int) and tid in staged_snapshots:
                        snap, _ = staged_snapshots[tid]
                        self.todos[idx] = snap
                        restored_todos.append(snap)
                if restored_todos and self._notification_dialog is not None:
                    self._notification_dialog.refresh_tasks_if_present(restored_todos)
                QMessageBox.warning(
                    self,
                    "保存失败",
                    "无法清除任务截止时间并保存到磁盘，所有修改已回滚。",
                )
                return

            snapshots: dict[int, tuple[dict[str, object], int]] = {}
            for int_id, (_, snapshot_data) in staged_snapshots.items():
                expected_rev = self._bump_schedule_revision(int_id)
                snapshots[int_id] = (snapshot_data, expected_rev)

            self._remove_notification_tasks(list(requested_ids))
            self.update_list_widget(changed_ids=changed_ids)
            if hasattr(self, "undo_toast_bar"):
                def _undo_clear_due() -> bool:
                    restored_ids: set[int] = set()
                    pre_undo_snapshots: dict[int, dict] = {}
                    for item in self.todos:
                        tid = item.get("id")
                        if isinstance(tid, int) and tid in snapshots:
                            snap_fields, expected_rev = snapshots[tid]
                            if self._schedule_revisions.get(tid, 0) != expected_rev:
                                continue
                            pre_undo_snapshots[tid] = copy.deepcopy(item)
                            item.update(snap_fields)
                            restored_ids.add(tid)
                    if not restored_ids:
                        return True
                    if not self._persist_todos():
                        restored_live: list[dict] = []
                        for item in self.todos:
                            tid = item.get("id")
                            if isinstance(tid, int) and tid in pre_undo_snapshots:
                                item.clear()
                                item.update(pre_undo_snapshots[tid])
                                restored_live.append(item)
                        if restored_live and self._notification_dialog is not None:
                            self._notification_dialog.refresh_tasks_if_present(restored_live)
                        QMessageBox.warning(
                            self,
                            "撤销失败",
                            "无法将恢复的截止时间写入磁盘，已保留撤销操作，请稍后重试。",
                        )
                        return False
                    for tid in restored_ids:
                        self._bump_schedule_revision(tid)
                    self._remove_notification_tasks(list(restored_ids))
                    self.update_list_widget(changed_ids=restored_ids)
                    return True

                self.undo_toast_bar.show_toast("已清除任务截止时间", _undo_clear_due)
        else:
            self._remove_notification_tasks(list(requested_ids))

    def _handle_notification_acknowledge(self, todo_ids: object) -> None:
        if isinstance(todo_ids, int):
            target_ids = [todo_ids]
        elif isinstance(todo_ids, (list, tuple, set)):
            target_ids = [int(tid) for tid in todo_ids]
        else:
            return
        self._remove_notification_tasks(target_ids)

    @Slot(object)
    def _handle_notification_edit(self, todo_id: object) -> None:
        self.activate_from_external_launch()
        self.handle_edit_request(todo_id)

    @Slot(object, object)
    def _handle_card_quick_snooze(self, todo_id: object, snooze_duration: object) -> None:
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is None or not isinstance(snooze_duration, timedelta):
            return
        self._handle_notification_snooze([normalized_id], snooze_duration)

    def _remove_notification_tasks(self, todo_ids: list[int]) -> None:
        if self._notification_dialog is not None:
            self._notification_dialog.remove_tasks(todo_ids)

    def _remove_notification_task(self, todo_id: object) -> None:
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is not None:
            self._remove_notification_tasks([normalized_id])

    def _restore_notification_dialog(self) -> None:
        if (
            self._notification_dialog is None
            or self._task_edit_dialog is not None
            or self._quitting_app
            or self.is_dnd_active()
        ):
            return
        if not self._notification_dialog.isVisible():
            self._notification_dialog.show()
        self._notification_dialog.raise_()
        self._pending_dnd_restore = False

    def _hide_notification_dialog(self) -> None:
        if self._notification_dialog is not None:
            self._notification_dialog.hide()

    def _close_notification_dialog(self) -> None:
        if self._notification_dialog is None:
            return
        dialog = self._notification_dialog
        dialog.close()
        if self._notification_dialog is dialog:
            self._notification_dialog = None

    def _ensure_window_visible_for_notification(self) -> None:
        if self._quitting_app:
            return
        current_state = self.windowState()
        if current_state & Qt.WindowState.WindowMinimized:
            self.setWindowState(current_state & ~Qt.WindowState.WindowMinimized)
            self.showNormal()
        elif self.isMinimized():
            self.showNormal()

        if self.isHidden() or not self.isVisible():
            self.show()

        self._force_window_foreground()

    def _force_window_foreground(self) -> None:
        self.raise_()
        self.activateWindow()

        app = QApplication.instance()
        if app is not None:
            app.setActiveWindow(self)

        window_handle = self.windowHandle()
        if window_handle is not None:
            window_handle.requestActivate()

        native_succeeded = False
        if sys.platform.startswith("win"):
            native_succeeded = self._force_foreground_windows()

        if not native_succeeded:
            self._temporarily_force_window_on_top()

    def _force_foreground_windows(self) -> bool:
        try:
            import ctypes

            hwnd = int(self.winId())
            if not hwnd:
                return False

            user32 = ctypes.windll.user32
            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.AllowSetForegroundWindow(-1)
            result = bool(user32.SetForegroundWindow(hwnd))
            if result:
                user32.BringWindowToTop(hwnd)
            return result
        except Exception as exc:  # pragma: no cover - 平台相关分支
            print(f"警告: Windows 前置窗口失败: {exc}")
            return False

    def _temporarily_force_window_on_top(self) -> None:
        if self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
            self._on_top_restore_timer.start(1000)
            return

        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.show()
        self._on_top_restore_timer.start(1000)

    def _restore_window_stays_on_top_flag(self) -> None:
        if getattr(self, "_always_on_top", False):
            return
        if not self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
            return

        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.show()

    @Slot(bool)
    def _on_pin_toggled(self, checked: bool) -> None:
        self._apply_pin_state(checked, persist=True)

    def _apply_pin_state(self, pinned: bool, *, persist: bool = True) -> None:
        pinned_bool = bool(pinned)
        self._always_on_top = pinned_bool
        if hasattr(self, "pin_button") and self.pin_button.isChecked() != pinned_bool:
            self.pin_button.blockSignals(True)
            self.pin_button.setChecked(pinned_bool)
            self.pin_button.blockSignals(False)
        currently_pinned = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if currently_pinned != pinned_bool:
            was_visible = self.isVisible()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned_bool)
            if was_visible:
                self.show()
        if persist:
            self.settings.setValue("windowAlwaysOnTop", pinned_bool)

    def _next_todo_id(self) -> int:
        current_ids = [t["id"] for t in self.todos if isinstance(t.get("id"), int)]
        max_id = max(current_ids) if current_ids else 0
        new_id_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        new_id = max(new_id_time, max_id + 1)
        existing_ids = set(current_ids)
        while new_id in existing_ids:
            new_id += 1
        return new_id

    def _is_storage_read_only(self) -> bool:
        return self._storage_status is not None and bool(self._storage_status.read_only)

    def _submit_quick_add(self, *, open_full_dialog: bool = False) -> None:
        text = self.quick_add_input.text().strip()
        if open_full_dialog:
            if self.show_add_task_dialog(initial_text=text):
                self.quick_add_input.clear()
            return
        if not text:
            return
        if self._is_storage_read_only():
            self._sync_storage_warning_banner()
            QMessageBox.warning(
                self,
                "只读恢复模式",
                "主数据文件当前处于损坏保护状态，请先在顶部警告横幅中备份并恢复可写，再添加任务。",
            )
            return
        new_id = self._next_todo_id()
        new_todo = {
            "id": new_id,
            "text": text,
            "priority": "中",
            "dueDate": None,
            "reminderOffset": -1,
            "completed": False,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "snoozeUntil": None,
            "notifiedForReminder": False,
            "notifiedForDue": False,
            "lastNotifiedAt": None,
        }
        self.todos.append(new_todo)
        self._persist_todos()
        self.update_list_widget(changed_ids={new_id})
        self.quick_add_input.clear()

    def _focus_quick_add(self) -> None:
        self.quick_add_input.setFocus()
        self.quick_add_input.selectAll()

    def _focus_search_input(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _handle_escape_shortcut(self) -> None:
        if self.search_input.text():
            self.search_input.clear()
        if self.search_input.hasFocus():
            self.search_input.clearFocus()
        elif hasattr(self, "undo_toast_bar") and self.undo_toast_bar.isVisible():
            self.undo_toast_bar.dismiss()

    def _handle_undo_shortcut(self) -> None:
        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, QLineEdit) and focus_widget.text():
            return
        if hasattr(self, "undo_toast_bar") and self.undo_toast_bar.has_active_undo():
            self.undo_toast_bar.trigger_undo()

    def _handle_delete_shortcut(self) -> None:
        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, QLineEdit):
            return
        current_item = self.list_widget.currentItem()
        if current_item is None:
            return
        widget = self.list_widget.itemWidget(current_item)
        if isinstance(widget, TodoItemWidget) and "id" in widget.todo_item:
            self.handle_delete_request(widget.todo_item["id"])

    @Slot(str)
    def _on_search_text_changed(self, _text: str) -> None:
        self.update_list_widget()

    def reset_filters_and_search(self) -> None:
        self._restoring_view_options = True
        try:
            self.filter_combo.setCurrentText("全部")
            self.search_input.clear()
            self.settings.setValue("filterOption", self.filter_combo.currentText())
        finally:
            self._restoring_view_options = False
        self.update_list_widget()

    # --- 任务操作 ---
    def _activate_task_editor(self) -> bool:
        dialog = self._task_edit_dialog
        if dialog is None:
            return False
        if dialog.isMinimized():
            dialog.showNormal()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return True

    @contextmanager
    def _task_editor_session(
        self,
        todo_item: Optional[dict] = None,
        *,
        initial_text: str = "",
    ) -> Iterator[TaskEditDialog]:
        # 编辑持有模态输入期间，提醒仅累积数据；保存/取消后再恢复同一批次。
        self._on_top_restore_timer.stop()
        self._restore_window_stays_on_top_flag()
        dialog = TaskEditDialog(todo_item=todo_item, parent=self, initial_text=initial_text)
        self._task_edit_dialog = dialog
        self._hide_notification_dialog()
        try:
            yield dialog
        finally:
            self._task_edit_dialog = None
            dialog.hide()
            dialog.deleteLater()
            if self.isVisible() and not self.isMinimized():
                self._restore_notification_dialog()

    def show_add_task_dialog(self, initial_text: str = "") -> bool:
        if self._activate_task_editor():
            return False
        accepted = False
        with self._task_editor_session(initial_text=initial_text) as dialog:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                accepted = True
                new_data = dialog.get_task_data()
                new_id = self._next_todo_id()

                new_todo = {
                    "id": new_id,
                    "text": new_data["text"],
                    "priority": new_data["priority"],
                    "dueDate": new_data["dueDate"],
                    "reminderOffset": new_data["reminderOffset"],
                    "recurrence": normalize_recurrence(new_data.get("recurrence")),
                    "completed": False,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "snoozeUntil": None,
                    "notifiedForReminder": False,
                    "notifiedForDue": False,
                    "lastNotifiedAt": None,
                }
                self.todos.append(new_todo)
                self._persist_todos()
                self.update_list_widget(changed_ids={new_id})
        return accepted

    def _normalize_todo_id(self, raw_id: object) -> Optional[int]:
        """尝试将传入的任务 ID 规范化为 Python int。"""
        try:
            return int(raw_id)
        except (TypeError, ValueError):
            print(f"警告: 收到无法识别的任务ID: {raw_id!r}")
            return None

    @Slot(object)
    def handle_edit_request(self, todo_id: object) -> None:
        if self._activate_task_editor():
            return
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is None:
            QMessageBox.warning(self, "错误", "收到无效的任务标识，无法编辑。")
            return

        todo_to_edit = next((t for t in self.todos if t.get("id") == normalized_id), None)
        if not todo_to_edit:
            QMessageBox.warning(self, "错误", "无法找到要编辑的任务。")
            return

        with self._task_editor_session(todo_to_edit) as dialog:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                updated_data = dialog.get_task_data()
                for index, todo in enumerate(self.todos):
                    if todo["id"] == normalized_id:
                        new_fields = build_edit_update_fields(todo, updated_data)
                        schedule_changed = any(
                            todo.get(field) != new_fields.get(field)
                            for field in ("dueDate", "reminderOffset", "recurrence", "snoozeUntil")
                            if field in new_fields
                        )
                        self.todos[index].update(new_fields)
                        if schedule_changed:
                            self._bump_schedule_revision(normalized_id)
                        self._remove_notification_task(normalized_id)
                        break

                self._persist_todos()
                self.update_list_widget(changed_ids={normalized_id})

    @Slot(object)
    def handle_delete_request(self, todo_id: object) -> None:
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is None:
            QMessageBox.warning(self, "错误", "收到无效的任务标识，无法删除。")
            return

        delete_index = next(
            (idx for idx, item in enumerate(self.todos) if item.get("id") == normalized_id),
            None,
        )
        if delete_index is None:
            print(f"警告: 删除任务时未找到ID {normalized_id}。")
            return

        removed_snapshot = copy.deepcopy(self.todos[delete_index])
        self._remove_notification_task(normalized_id)
        del self.todos[delete_index]
        self._persist_todos()
        self.update_list_widget(changed_ids={normalized_id})

        if hasattr(self, "undo_toast_bar"):
            raw_text = str(removed_snapshot.get("text", ""))
            preview = raw_text[:18] + ("…" if len(raw_text) > 18 else "")

            def _undo_delete() -> bool:
                if any(item.get("id") == normalized_id for item in self.todos):
                    return True
                insert_at = min(max(delete_index, 0), len(self.todos))
                self.todos.insert(insert_at, copy.deepcopy(removed_snapshot))
                if not self._persist_todos():
                    if insert_at < len(self.todos) and self.todos[insert_at].get("id") == normalized_id:
                        del self.todos[insert_at]
                    else:
                        self.todos = [item for item in self.todos if item.get("id") != normalized_id]
                    QMessageBox.warning(
                        self,
                        "撤销失败",
                        "无法恢复删除的任务到磁盘，已保留撤销操作，请稍后重试。",
                    )
                    return False
                self.update_list_widget(changed_ids={normalized_id})
                return True

            self.undo_toast_bar.show_toast(f"已删除「{preview}」", _undo_delete)

    @Slot(object)
    def handle_toggle_complete_request(self, todo_id: object) -> None:
        self.toggle_complete_todo(todo_id)

    @Slot(object)
    def handle_finish_recurrence_request(self, todo_id: object) -> None:
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is None:
            print(f"警告: 结束重复任务时收到无效ID: {todo_id!r}")
            return
        snapshot: Optional[dict] = None
        target_index: Optional[int] = None
        for idx, todo in enumerate(self.todos):
            if todo.get("id") == normalized_id:
                snapshot = copy.deepcopy(todo)
                target_index = idx
                todo.update(
                    {
                        "completed": True,
                        "recurrence": None,
                        "snoozeUntil": None,
                        "notifiedForReminder": True,
                        "notifiedForDue": True,
                    }
                )
                break
        if snapshot is None or target_index is None:
            return
        if not self._persist_todos():
            self.todos[target_index] = snapshot
            if self._notification_dialog is not None:
                self._notification_dialog.refresh_tasks_if_present([snapshot])
            QMessageBox.warning(
                self,
                "保存失败",
                "无法保存结束重复状态到磁盘，所有修改已回滚。",
            )
            return

        expected_rev = self._bump_schedule_revision(normalized_id)
        self._remove_notification_task(normalized_id)
        self.update_list_widget(changed_ids={normalized_id})
        if hasattr(self, "undo_toast_bar"):
            raw_text = str(snapshot.get("text", ""))
            preview = raw_text[:18] + ("…" if len(raw_text) > 18 else "")

            def _undo_finish() -> bool:
                if self._schedule_revisions.get(normalized_id, 0) != expected_rev:
                    return True
                for idx, item in enumerate(self.todos):
                    if item.get("id") == normalized_id:
                        pre_undo_snapshot = copy.deepcopy(item)
                        item.update(
                            {
                                "completed": bool(snapshot.get("completed", False)),
                                "recurrence": copy.deepcopy(snapshot.get("recurrence")),
                                "snoozeUntil": snapshot.get("snoozeUntil"),
                                "notifiedForReminder": bool(
                                    snapshot.get("notifiedForReminder", False)
                                ),
                                "notifiedForDue": bool(snapshot.get("notifiedForDue", False)),
                            }
                        )
                        if not self._persist_todos():
                            item.clear()
                            item.update(pre_undo_snapshot)
                            if self._notification_dialog is not None:
                                self._notification_dialog.refresh_tasks_if_present([item])
                            QMessageBox.warning(
                                self,
                                "撤销失败",
                                "无法将撤销后的重复规则写入磁盘，已保留撤销操作，请稍后重试。",
                            )
                            return False
                        self._bump_schedule_revision(normalized_id)
                        self._remove_notification_task(normalized_id)
                        self.update_list_widget(changed_ids={normalized_id})
                        return True
                return True

            self.undo_toast_bar.show_toast(f"已结束重复「{preview}」", _undo_finish)

    def toggle_complete_todo(self, todo_id: object, called_from_notification: bool = False) -> None:
        del called_from_notification
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is None:
            print(f"警告: 尝试切换任务完成状态时收到无效ID: {todo_id!r}")
            return

        changed = False
        target_index: Optional[int] = None
        completed_snapshot: Optional[dict] = None
        became_completed = False
        advanced_recurrence = False
        now_utc = datetime.now(timezone.utc)
        for index, todo in enumerate(self.todos):
            if todo.get("id") == normalized_id:
                completed_snapshot = copy.deepcopy(todo)
                target_index = index
                if not todo.get("completed", False):
                    try:
                        changed, advanced_recurrence = self._complete_todo_in_place(
                            todo, now_utc=now_utc
                        )
                    except (OverflowError, ValueError) as exc:
                        QMessageBox.warning(
                            self,
                            "周期推进失败",
                            f"无法计算下一次重复截止时间，任务状态保持不变：\n{exc}",
                        )
                        return
                    became_completed = not advanced_recurrence
                else:
                    self.todos[index].update(
                        {
                            "completed": False,
                            "notifiedForReminder": False,
                            "notifiedForDue": False,
                            "lastNotifiedAt": None,
                        }
                    )
                    changed = True
                break

        if changed and target_index is not None and completed_snapshot is not None:
            if not self._persist_todos():
                self.todos[target_index] = completed_snapshot
                if self._notification_dialog is not None:
                    self._notification_dialog.refresh_tasks_if_present([completed_snapshot])
                QMessageBox.warning(
                    self,
                    "保存失败",
                    "无法保存任务完成状态到磁盘，所有修改已回滚。",
                )
                return

            expected_rev = self._bump_schedule_revision(normalized_id)
            if not completed_snapshot.get("completed", False):
                self._remove_notification_task(normalized_id)
            self.update_list_widget(changed_ids={normalized_id})
            current_filter = self.filter_combo.currentText()
            hides_completed = current_filter in ("未完成", "今天到期", "已逾期", "高优先级")
            should_offer_undo = (
                hasattr(self, "undo_toast_bar")
                and (advanced_recurrence or (became_completed and hides_completed))
            )
            if should_offer_undo:
                raw_text = str(completed_snapshot.get("text", ""))
                preview = raw_text[:18] + ("…" if len(raw_text) > 18 else "")
                toast_text = (
                    f"已完成本轮「{preview}」，已安排下一次"
                    if advanced_recurrence
                    else f"已完成「{preview}」"
                )

                def _undo_complete() -> bool:
                    if self._schedule_revisions.get(normalized_id, 0) != expected_rev:
                        return True
                    for idx, item in enumerate(self.todos):
                        if item.get("id") == normalized_id:
                            pre_undo_snapshot = copy.deepcopy(item)
                            restore_fields = {
                                "completed": bool(completed_snapshot.get("completed", False)),
                                "snoozeUntil": completed_snapshot.get("snoozeUntil"),
                                "notifiedForReminder": bool(
                                    completed_snapshot.get("notifiedForReminder", False)
                                ),
                                "notifiedForDue": bool(
                                    completed_snapshot.get("notifiedForDue", False)
                                ),
                                "lastNotifiedAt": completed_snapshot.get("lastNotifiedAt"),
                            }
                            if advanced_recurrence:
                                restore_fields["dueDate"] = completed_snapshot.get("dueDate")
                                restore_fields["recurrence"] = copy.deepcopy(
                                    completed_snapshot.get("recurrence")
                                )
                            item.update(restore_fields)
                            if not self._persist_todos():
                                item.clear()
                                item.update(pre_undo_snapshot)
                                if self._notification_dialog is not None:
                                    self._notification_dialog.refresh_tasks_if_present([item])
                                QMessageBox.warning(
                                    self,
                                    "撤销失败",
                                    "无法将撤销后的任务状态写入磁盘，已保留撤销操作，请稍后重试。",
                                )
                                return False
                            self._bump_schedule_revision(normalized_id)
                            self._remove_notification_task(normalized_id)
                            self.update_list_widget(changed_ids={normalized_id})
                            return True
                    return True

                self.undo_toast_bar.show_toast(toast_text, _undo_complete)
        else:
            print(f"警告: 切换ID {normalized_id} 任务完成状态时未找到。")

    # --- 列表刷新 ---
    def update_list_widget(
        self,
        _selection: object = None,
        *,
        changed_ids: Optional[Iterable[int]] = None,
    ) -> None:
        """协调目标列表顺序，同时复用未变化的任务卡片。"""

        del _selection
        self.list_widget.stop_scrolling()
        if not isinstance(self.todos, list):
            self.todos = []

        working_copy = [
            item.copy()
            for item in self.todos
            if isinstance(item, dict) and "id" in item
        ]
        processed = self._sort_todos(self._filter_todos(working_copy))
        if not self._todo_list_mapping_is_consistent():
            self._rebuild_todo_list(processed)
            return

        normalized_changed_ids = (
            None
            if changed_ids is None
            else {int(todo_id) for todo_id in changed_ids}
        )
        anchor = self._capture_scroll_anchor()
        previous_viewport_width = self.list_widget.viewport().width()
        target_ids = [int(todo["id"]) for todo in processed]
        if len(target_ids) != len(set(target_ids)):
            raise RuntimeError("筛选和排序结果中存在重复任务 ID")

        target_id_set = set(target_ids)
        structure_changed = False
        layout_changed = False

        self._reconciling_todo_list = True
        try:
            for todo_id in tuple(self._todo_items_by_id):
                if todo_id not in target_id_set:
                    self._remove_todo_list_entry(todo_id)
                    structure_changed = True

            if not processed:
                self._show_empty_list_message()
                structure_changed = True
            else:
                if self._remove_empty_placeholder():
                    structure_changed = True

                for target_row, todo_data in enumerate(processed):
                    todo_id = int(todo_data["id"])
                    list_item = self._todo_items_by_id.get(todo_id)
                    item_widget = self._todo_widgets_by_id.get(todo_id)
                    if list_item is None or item_widget is None:
                        list_item, item_widget = self._create_todo_list_entry(
                            todo_data,
                            target_row,
                        )
                        structure_changed = True
                        layout_changed = True
                    else:
                        should_update = (
                            normalized_changed_ids is None
                            or todo_id in normalized_changed_ids
                        )
                        if should_update and item_widget.update_todo(todo_data):
                            layout_changed = (
                                self._sync_todo_card_size(list_item, item_widget)
                                or layout_changed
                            )

                    current_row = self.list_widget.row(list_item)
                    if current_row != target_row:
                        self._move_todo_list_entry(
                            todo_id,
                            target_row,
                        )
                        structure_changed = True
        finally:
            self._reconciling_todo_list = False

        if structure_changed or layout_changed:
            self.list_widget.doItemsLayout()
        if self.list_widget.viewport().width() != previous_viewport_width:
            self._sync_todo_card_sizes()
        self._restore_scroll_anchor(anchor)
        self._refresh_visible_todo_timers()
        self._update_status_summary()

    def _todo_list_mapping_is_consistent(self) -> bool:
        """确认映射、列表项和卡片仍描述同一组可见任务。"""

        if self._todo_items_by_id.keys() != self._todo_widgets_by_id.keys():
            return False

        placeholder_count = 0
        if self._empty_placeholder_item is not None:
            if self.list_widget.row(self._empty_placeholder_item) < 0:
                return False
            if (
                self.list_widget.itemWidget(self._empty_placeholder_item)
                is not self._empty_placeholder_widget
            ):
                return False
            placeholder_count = 1
        elif any(
            placeholder is not None
            for placeholder in (
                self._empty_placeholder_widget,
                self._empty_placeholder_label,
                self._empty_reset_button,
            )
        ):
            return False

        if self.list_widget.count() != len(self._todo_items_by_id) + placeholder_count:
            return False

        for todo_id, list_item in self._todo_items_by_id.items():
            item_widget = self._todo_widgets_by_id[todo_id]
            if self.list_widget.row(list_item) < 0:
                return False
            if self.list_widget.itemWidget(list_item) is not item_widget:
                return False
            if item_widget.todo_item.get("id") != todo_id:
                return False
        return True

    def _create_todo_list_entry(
        self,
        todo_data: dict,
        target_row: int,
    ) -> tuple[QListWidgetItem, TodoItemWidget]:
        """创建一张任务卡片并只连接一次操作信号。"""

        todo_id = int(todo_data["id"])
        list_item = QListWidgetItem()
        item_widget = TodoItemWidget(todo_data.copy(), palette=self._palette)
        item_widget.request_edit.connect(self.handle_edit_request)
        item_widget.request_delete.connect(self.handle_delete_request)
        item_widget.request_toggle_complete.connect(
            self.handle_toggle_complete_request
        )
        item_widget.request_quick_snooze.connect(self._handle_card_quick_snooze)
        item_widget.request_finish_recurrence.connect(
            self.handle_finish_recurrence_request
        )
        widget_size_hint = item_widget.sizeHint()
        item_height = max(widget_size_hint.height(), item_widget.minimumHeight())
        list_item.setSizeHint(QSize(0, item_height))
        self.list_widget.insertItem(target_row, list_item)
        self.list_widget.setItemWidget(list_item, item_widget)
        self._todo_items_by_id[todo_id] = list_item
        self._todo_widgets_by_id[todo_id] = item_widget
        self._sync_todo_card_size(list_item, item_widget)
        return list_item, item_widget

    def _remove_todo_list_entry(self, todo_id: int) -> None:
        """移除一张卡片及其映射，并安排释放完整子对象树。"""

        list_item = self._todo_items_by_id.pop(todo_id, None)
        item_widget = self._todo_widgets_by_id.pop(todo_id, None)
        if list_item is None:
            return
        row = self.list_widget.row(list_item)
        if row >= 0:
            self.list_widget.removeItemWidget(list_item)
            removed_item = self.list_widget.takeItem(row)
            del removed_item
        if item_widget is not None:
            item_widget.deleteLater()

    def _move_todo_list_entry(self, todo_id: int, target_row: int) -> None:
        """移动现有列表项，不重建其卡片或重复连接信号。"""

        list_item = self._todo_items_by_id[todo_id]
        item_widget = self._todo_widgets_by_id[todo_id]
        current_row = self.list_widget.row(list_item)
        if current_row < 0 or current_row == target_row:
            return
        self.list_widget.removeItemWidget(list_item)
        moved_item = self.list_widget.takeItem(current_row)
        self.list_widget.insertItem(target_row, moved_item)
        self.list_widget.setItemWidget(moved_item, item_widget)

    def _sync_todo_card_size(
        self,
        list_item: QListWidgetItem,
        item_widget: TodoItemWidget,
    ) -> bool:
        """只同步新建或视觉发生变化的目标卡片高度。"""

        viewport = self.list_widget.viewport()
        if calculate_card_width(
            viewport.width(),
            self.list_widget.spacing(),
        ) <= 0:
            return False
        layout_result = item_widget.refresh_layout(
            viewport_width=viewport.width(),
            list_spacing=self.list_widget.spacing(),
        )
        target_hint = QSize(0, layout_result.card_height)
        if list_item.sizeHint() == target_hint:
            return False
        list_item.setSizeHint(target_hint)
        return True

    def _capture_scroll_anchor(self) -> tuple[Optional[int], int, int]:
        """记录首个可见任务及其像素偏移，供差量更新后恢复。"""

        scrollbar = self.list_widget.verticalScrollBar()
        for row in range(self.list_widget.count()):
            list_item = self.list_widget.item(row)
            item_widget = self.list_widget.itemWidget(list_item)
            if not isinstance(item_widget, TodoItemWidget):
                continue
            item_rect = self.list_widget.visualItemRect(list_item)
            if item_rect.bottom() >= 0:
                return (
                    int(item_widget.todo_item["id"]),
                    item_rect.top(),
                    scrollbar.value(),
                )
        return None, 0, scrollbar.value()

    def _restore_scroll_anchor(
        self,
        anchor: tuple[Optional[int], int, int],
    ) -> None:
        """在目标任务仍存在时保持其原像素位置，否则保留旧滚动值。"""

        todo_id, previous_top, previous_value = anchor
        scrollbar = self.list_widget.verticalScrollBar()
        if todo_id is None or todo_id not in self._todo_items_by_id:
            scrollbar.setValue(
                min(max(previous_value, scrollbar.minimum()), scrollbar.maximum())
            )
            return

        list_item = self._todo_items_by_id[todo_id]
        current_top = self.list_widget.visualItemRect(list_item).top()
        target_value = scrollbar.value() + current_top - previous_top
        scrollbar.setValue(
            min(max(target_value, scrollbar.minimum()), scrollbar.maximum())
        )

    def _rebuild_todo_list(self, processed: list[dict]) -> None:
        """映射异常时执行一次完整恢复；正常 CRUD 不进入此路径。"""

        self.list_widget.clear()
        self._todo_items_by_id.clear()
        self._todo_widgets_by_id.clear()
        self._empty_placeholder_item = None
        self._empty_placeholder_widget = None
        self._empty_placeholder_label = None
        self._empty_reset_button = None
        if not processed:
            self._show_empty_list_message()
            self._update_status_summary()
            return

        for target_row, todo_data in enumerate(processed):
            self._create_todo_list_entry(todo_data, target_row)

        self._sync_todo_card_sizes()
        self._update_status_summary()

    def _sync_todo_card_sizes(self) -> None:
        """按最终 viewport 宽度同步卡片与 QListWidgetItem 的动态高度。"""

        if self._syncing_todo_card_sizes or not hasattr(self, "list_widget"):
            return

        viewport = self.list_widget.viewport()
        if calculate_card_width(
            viewport.width(),
            self.list_widget.spacing(),
        ) <= 0:
            return

        self._syncing_todo_card_sizes = True
        try:
            self.list_widget.doItemsLayout()
            changed = False
            for index in range(self.list_widget.count()):
                list_item = self.list_widget.item(index)
                item_widget = self.list_widget.itemWidget(list_item)
                if not isinstance(item_widget, TodoItemWidget):
                    continue

                layout_result = item_widget.refresh_layout(
                    viewport_width=viewport.width(),
                    list_spacing=self.list_widget.spacing(),
                )
                target_hint = QSize(0, layout_result.card_height)
                if list_item.sizeHint() != target_hint:
                    list_item.setSizeHint(target_hint)
                    changed = True

            if changed:
                self.list_widget.doItemsLayout()
        finally:
            self._syncing_todo_card_sizes = False
        self._refresh_visible_todo_timers()

    def _empty_list_message_text(self) -> str:
        if not self.todos:
            return "🎉 暂无待办事项！"
        search_query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        filter_text = self.filter_combo.currentText()
        if search_query:
            return f"「{filter_text}」下未找到包含“{search_query}”的任务"
        return f"当前「{filter_text}」下暂无任务"

    def _has_active_view_filters(self) -> bool:
        filter_active = self.filter_combo.currentText() != "全部"
        search_active = bool(self.search_input.text().strip()) if hasattr(self, "search_input") else False
        return bool(self.todos) and (filter_active or search_active)

    def _show_empty_list_message(self) -> None:
        message = self._empty_list_message_text()
        show_reset = self._has_active_view_filters()
        if self._empty_placeholder_item is not None:
            if self._empty_placeholder_label is not None:
                self._empty_placeholder_label.setText(message)
            if self._empty_reset_button is not None:
                self._empty_reset_button.setVisible(show_reset)
            self._update_empty_placeholder_geometry()
            return

        empty_item = QListWidgetItem()
        empty_container = QWidget()
        container_layout = QVBoxLayout(empty_container)
        container_layout.setContentsMargins(0, 40, 0, 40)
        container_layout.setSpacing(10)
        container_layout.addStretch()

        empty_label = QLabel(message)
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setWordWrap(True)
        empty_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        container_layout.addWidget(empty_label, alignment=Qt.AlignmentFlag.AlignCenter)

        reset_button = QPushButton("重置筛选与搜索")
        reset_button.setObjectName("resetFilterButton")
        reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_button.setVisible(show_reset)
        reset_button.clicked.connect(self.reset_filters_and_search)
        container_layout.addWidget(reset_button, alignment=Qt.AlignmentFlag.AlignCenter)
        container_layout.addStretch()

        self.list_widget.addItem(empty_item)
        self.list_widget.setItemWidget(empty_item, empty_container)

        self._empty_placeholder_item = empty_item
        self._empty_placeholder_widget = empty_container
        self._empty_placeholder_label = empty_label
        self._empty_reset_button = reset_button
        self._apply_palette(self._palette)
        self._update_empty_placeholder_geometry()
        QTimer.singleShot(0, self._update_empty_placeholder_geometry)

    def _remove_empty_placeholder(self) -> bool:
        """移除空列表占位，不触碰已有任务卡片。"""

        empty_item = self._empty_placeholder_item
        empty_widget = self._empty_placeholder_widget
        if empty_item is None:
            return False

        row = self.list_widget.row(empty_item)
        if row >= 0:
            self.list_widget.removeItemWidget(empty_item)
            removed_item = self.list_widget.takeItem(row)
            del removed_item
        if empty_widget is not None:
            empty_widget.deleteLater()
        self._empty_placeholder_item = None
        self._empty_placeholder_widget = None
        self._empty_placeholder_label = None
        self._empty_reset_button = None
        return True

    def _update_status_summary(self) -> None:
        if not isinstance(self.todos, list):
            return
        now_utc = datetime.now(timezone.utc)
        incomplete_count = 0
        overdue_count = 0
        for todo in self.todos:
            if not isinstance(todo, dict) or todo.get("completed", False):
                continue
            incomplete_count += 1
            due_utc = self._parse_iso_datetime(todo.get("dueDate"))
            if due_utc is not None and due_utc <= now_utc:
                overdue_count += 1

        if not self.todos:
            summary_text = "暂无待办"
        elif incomplete_count == 0:
            summary_text = f"全部已完成 ({len(self.todos)})"
        elif overdue_count > 0:
            summary_text = f"待办 {incomplete_count} · 逾期 {overdue_count}"
        else:
            summary_text = f"待办 {incomplete_count}"

        if self.is_dnd_active(now_utc=now_utc):
            summary_text = f"{summary_text} · 勿扰"

        if hasattr(self, "status_summary_label"):
            self.status_summary_label.setText(summary_text)
        if hasattr(self, "tray_icon"):
            self.tray_icon.setToolTip(f"{APP_NAME} ({summary_text})")

    @staticmethod
    def _parse_iso_datetime(value: object) -> Optional[datetime]:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        try:
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except OverflowError:
            return None

    def _filter_todos(self, todos_list: List[dict]) -> List[dict]:
        filter_text = self.filter_combo.currentText()
        search_query = (
            self.search_input.text().strip().lower()
            if hasattr(self, "search_input")
            else ""
        )
        now_utc = datetime.now(timezone.utc)
        today_local = now_utc.astimezone().date()
        filtered: List[dict] = []
        for todo in todos_list:
            add = False
            is_completed = bool(todo.get("completed", False))
            if filter_text == "全部":
                add = True
            elif filter_text == "未完成":
                add = not is_completed
            elif filter_text == "已完成":
                add = is_completed
            elif filter_text == "今天到期" and not is_completed:
                due_utc = self._parse_iso_datetime(todo.get("dueDate"))
                if due_utc is not None and due_utc.astimezone().date() <= today_local:
                    add = True
            elif filter_text == "已逾期" and not is_completed:
                due_utc = self._parse_iso_datetime(todo.get("dueDate"))
                if due_utc is not None and due_utc <= now_utc:
                    add = True
            elif filter_text == "高优先级" and not is_completed and todo.get("priority") == "高":
                add = True
            if add and search_query:
                if search_query not in str(todo.get("text", "")).lower():
                    add = False
            if add:
                filtered.append(todo)
        return filtered

    def _sort_todos(self, todos_list: List[dict]) -> List[dict]:
        sort_key = self.sort_combo.currentText()

        def get_created_ts(todo: dict) -> float:
            created = self._parse_iso_datetime(todo.get("createdAt"))
            return created.timestamp() if created is not None else 0.0

        def get_due_ts(todo: dict) -> Optional[float]:
            due = self._parse_iso_datetime(todo.get("dueDate"))
            return due.timestamp() if due is not None else None

        priority_value = lambda p: {"高": 0, "中": 1, "低": 2}.get(p, 3)

        if sort_key == "创建时间 (新->旧)":
            return sorted(
                todos_list,
                key=lambda t: (
                    bool(t.get("completed", False)),
                    -get_created_ts(t),
                ),
            )
        if sort_key == "创建时间 (旧->新)":
            return sorted(
                todos_list,
                key=lambda t: (
                    bool(t.get("completed", False)),
                    get_created_ts(t),
                ),
            )
        if sort_key == "截止日期 (近->远)":
            return sorted(
                todos_list,
                key=lambda t: (
                    bool(t.get("completed", False)),
                    (due_ts := get_due_ts(t)) is None,
                    due_ts if due_ts is not None else 0.0,
                ),
            )
        if sort_key == "截止日期 (远->近)":
            return sorted(
                todos_list,
                key=lambda t: (
                    bool(t.get("completed", False)),
                    (due_ts := get_due_ts(t)) is None,
                    -(due_ts if due_ts is not None else 0.0),
                ),
            )
        if sort_key == "优先级 (高->低)":
            return sorted(
                todos_list,
                key=lambda t: (
                    bool(t.get("completed", False)),
                    priority_value(t.get("priority", "中")),
                    (due_ts := get_due_ts(t)) is None,
                    due_ts if due_ts is not None else 0.0,
                ),
            )
        return todos_list

    # --- 托盘 ---
    def _create_tray_icon(self) -> None:
        self.tray_icon = QSystemTrayIcon(get_icon(APP_ICON_PATH, "TD"), self)
        self.tray_icon.setToolTip(APP_NAME)
        tray_menu = QMenu(self)
        tray_menu.addAction("显示/隐藏窗口", self.toggle_window_visibility)
        tray_menu.addAction("快速添加任务...", self.quick_add_from_tray)
        tray_menu.addSeparator()
        self.tray_dnd_action = tray_menu.addAction("勿扰模式")
        self.tray_dnd_action.setCheckable(True)
        self.tray_dnd_action.setChecked(self._dnd_enabled)
        self.tray_dnd_action.toggled.connect(self.set_dnd_enabled)
        tray_menu.addAction("勿扰 1 小时", self.enable_dnd_for_one_hour)
        tray_menu.addAction("设置与工具...", self.open_settings_dialog)
        tray_menu.addSeparator()
        tray_menu.addAction("退出应用", self.quit_application)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
        self.tray_icon.show()

    def quick_add_from_tray(self) -> None:
        if self.isHidden() or self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        self.show_add_task_dialog()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() != QEvent.Type.WindowStateChange or self._quitting_app:
            return

        old_state = event.oldState() if hasattr(event, "oldState") else Qt.WindowState.WindowNoState
        tray_icon = getattr(self, "tray_icon", None)
        if (
            self.isMinimized()
            and not self.isHidden()
            and tray_icon
            and tray_icon.isVisible()
            and not (old_state & Qt.WindowState.WindowMinimized)
        ):
            QTimer.singleShot(0, self._minimize_to_tray)
        elif old_state & Qt.WindowState.WindowMinimized and not self.isMinimized():
            self._refresh_visible_todo_timers()

    def _minimize_to_tray(self) -> None:
        if self._quitting_app:
            return
        self._hide_notification_dialog()
        self.hide()

    def _on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window_visibility()

    @Slot()
    def activate_from_external_launch(self) -> None:
        """从重复启动或提醒弹窗请求唤醒并前置主窗口。"""

        if self._quitting_app:
            return
        if self.isHidden() or self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        self._restore_notification_dialog()
        self._refresh_visible_todo_timers()

    def toggle_window_visibility(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self._hide_notification_dialog()
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self._restore_notification_dialog()

    @staticmethod
    def _coerce_bool_setting(raw_value: object, default: bool) -> bool:
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, int):
            return bool(raw_value)
        if isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered in ("true", "1", "yes"):
                return True
            if lowered in ("false", "0", "no"):
                return False
        return default

    # --- 设置、勿扰与数据维护 ---
    def is_dnd_active(self, *, now_utc: Optional[datetime] = None) -> bool:
        if not self._dnd_enabled:
            return False
        if self._dnd_until_utc is None:
            return True
        current = now_utc or datetime.now(timezone.utc)
        if current < self._dnd_until_utc:
            return True
        self._dnd_enabled = False
        self._dnd_until_utc = None
        self.settings.setValue("dndEnabled", False)
        self.settings.setValue("dndUntilUtc", "")
        if self._notification_dialog is not None and not self._notification_dialog.isVisible():
            self._pending_dnd_restore = True
        self._sync_dnd_ui()
        return False

    def _format_dnd_status_text(self, active: bool) -> str:
        if not active:
            return "未开启"
        if self._dnd_until_utc is None:
            return "已开启（手动）"
        local_until = self._dnd_until_utc.astimezone().strftime("%H:%M")
        return f"已开启（至 {local_until}）"

    def dnd_status_text(self) -> str:
        return self._format_dnd_status_text(self.is_dnd_active())

    def _sync_dnd_ui(self) -> None:
        active = self._dnd_enabled and (
            self._dnd_until_utc is None or datetime.now(timezone.utc) < self._dnd_until_utc
        )
        if hasattr(self, "tray_dnd_action"):
            self.tray_dnd_action.blockSignals(True)
            self.tray_dnd_action.setChecked(active)
            self.tray_dnd_action.blockSignals(False)
        settings_dialog = getattr(self, "_settings_dialog", None)
        if settings_dialog is not None:
            settings_dialog.dnd_checkbox.blockSignals(True)
            settings_dialog.dnd_checkbox.setChecked(active)
            settings_dialog.dnd_checkbox.blockSignals(False)
            settings_dialog.dnd_status_label.setText(
                f"当前勿扰状态：{self._format_dnd_status_text(active)}"
            )
        self._update_status_summary()

    def set_theme_preference(self, preference: str | ThemePreference) -> None:
        coerced = ThemePreference.coerce(preference)
        self.theme_manager.set_preference(coerced)
        self.settings.setValue("themePreference", coerced.value)
        self.settings.sync()

    def set_sound_enabled(self, enabled: bool) -> None:
        self._sound_enabled = bool(enabled)
        self.settings.setValue("soundEnabled", self._sound_enabled)
        self.settings.sync()

    def set_dnd_enabled(self, enabled: bool) -> None:
        self._dnd_enabled = bool(enabled)
        self._dnd_until_utc = None
        self.settings.setValue("dndEnabled", self._dnd_enabled)
        self.settings.setValue("dndUntilUtc", "")
        self.settings.sync()
        if self._dnd_enabled:
            self._pending_dnd_restore = False
            self._hide_notification_dialog()
        elif self.isVisible() and not self.isMinimized():
            self._restore_notification_dialog()
        elif self._notification_dialog is not None and not self._notification_dialog.isVisible():
            self._pending_dnd_restore = True
        self._sync_dnd_ui()

    def enable_dnd_for_one_hour(self) -> None:
        until_utc = datetime.now(timezone.utc) + timedelta(hours=1)
        self._dnd_enabled = True
        self._dnd_until_utc = until_utc
        self._pending_dnd_restore = False
        self.settings.setValue("dndEnabled", True)
        self.settings.setValue("dndUntilUtc", until_utc.isoformat())
        self.settings.sync()
        self._hide_notification_dialog()
        self._sync_dnd_ui()

    def _set_autostart_enabled(self, enabled: bool, dialog: Optional[SettingsDialog] = None) -> None:
        desired = bool(enabled)
        try:
            actual = set_autostart_enabled(desired)
            succeeded = actual == desired
        except OSError as exc:
            succeeded = False
            print(f"警告: 更新开机自启配置失败: {exc}")
        if not succeeded:
            QMessageBox.warning(self, "自启设置失败", "未能更新 Windows 开机自启注册表项。")
            if dialog is not None:
                dialog.autostart_checkbox.blockSignals(True)
                dialog.autostart_checkbox.setChecked(is_autostart_enabled())
                dialog.autostart_checkbox.blockSignals(False)

    def _register_or_defer_undo(
        self,
        message: str,
        callback,
        *,
        defer: bool,
    ) -> None:
        if defer:
            self._deferred_undo_toast = (message, callback)
        elif hasattr(self, "undo_toast_bar"):
            self.undo_toast_bar.show_toast(message, callback)

    def _flush_deferred_undo_toast(self) -> None:
        payload = self._deferred_undo_toast
        self._deferred_undo_toast = None
        if payload is not None and hasattr(self, "undo_toast_bar"):
            message, callback = payload
            self.undo_toast_bar.show_toast(message, callback)

    def _validate_imported_todo_item(self, raw_item: object, index: int) -> None:
        if not isinstance(raw_item, dict):
            raise ValueError(f"第 {index + 1} 条任务必须是 JSON 对象。")
        if not isinstance(raw_item.get("text"), str):
            raise ValueError(f"第 {index + 1} 条任务的 text 字段必须为字符串。")
        priority = raw_item.get("priority")
        if priority is not None and priority not in ("高", "中", "低"):
            raise ValueError(f"第 {index + 1} 条任务的 priority 无效：{priority!r}。")
        completed = raw_item.get("completed")
        if completed is not None and not isinstance(completed, bool):
            raise ValueError(f"第 {index + 1} 条任务的 completed 必须为布尔值。")
        created_at = raw_item.get("createdAt")
        if created_at is not None:
            if not isinstance(created_at, str) or self._parse_iso_datetime(created_at) is None:
                raise ValueError(f"第 {index + 1} 条任务的 createdAt 不是有效的 ISO 日期时间或超出支持范围。")
        due_date = raw_item.get("dueDate")
        parsed_due_utc: Optional[datetime] = None
        if due_date is not None:
            if not isinstance(due_date, str):
                raise ValueError(f"第 {index + 1} 条任务的 dueDate 不是有效的 ISO 日期时间。")
            parsed_due_utc = self._parse_iso_datetime(due_date)
            if parsed_due_utc is None:
                raise ValueError(f"第 {index + 1} 条任务的 dueDate 不是有效的 ISO 日期时间或超出支持范围。")
        if "reminderOffset" in raw_item:
            reminder_offset = raw_item.get("reminderOffset")
            if isinstance(reminder_offset, bool) or not isinstance(reminder_offset, int):
                raise ValueError(f"第 {index + 1} 条任务的 reminderOffset 必须为整数。")
            if reminder_offset not in REMINDER_SECONDS_TO_TEXT_MAP:
                raise ValueError(f"第 {index + 1} 条任务的 reminderOffset 超出支持的提醒选项：{reminder_offset!r}。")
            if parsed_due_utc is not None and reminder_offset >= 0:
                try:
                    _ = parsed_due_utc - timedelta(seconds=reminder_offset)
                except OverflowError as exc:
                    raise ValueError(
                        f"第 {index + 1} 条任务的 reminderOffset 与 dueDate 组合超出支持时间范围。"
                    ) from exc
        snooze_until = raw_item.get("snoozeUntil")
        if snooze_until is not None:
            if not isinstance(snooze_until, str) or self._parse_iso_datetime(snooze_until) is None:
                raise ValueError(f"第 {index + 1} 条任务的 snoozeUntil 必须为有效的 ISO 日期时间或 null。")

    def clear_completed_todos(self, *, defer_undo_toast: bool = False) -> int:
        if self._is_storage_read_only():
            self._sync_storage_warning_banner()
            raise RuntimeError("只读恢复模式下无法清理任务，请先恢复可写存储。")
        removed_entries = [
            (idx, copy.deepcopy(item))
            for idx, item in enumerate(self.todos)
            if isinstance(item, dict) and item.get("completed", False)
        ]
        if not removed_entries:
            return 0
        previous_todos = copy.deepcopy(self.todos)
        self.todos = [
            item
            for item in self.todos
            if not (isinstance(item, dict) and item.get("completed", False))
        ]
        if not self._persist_todos():
            self.todos = previous_todos
            raise RuntimeError("写入待办文件失败，已回滚清理操作。")
        self.update_list_widget()

        def _undo_clear() -> bool:
            previous_todos = copy.deepcopy(self.todos)
            existing_ids = {
                int(t["id"])
                for t in self.todos
                if isinstance(t, dict) and isinstance(t.get("id"), int)
            }
            restored_any = False
            for orig_idx, entry in removed_entries:
                entry_id = entry.get("id")
                if isinstance(entry_id, int) and entry_id in existing_ids:
                    continue
                insert_at = min(max(orig_idx, 0), len(self.todos))
                self.todos.insert(insert_at, copy.deepcopy(entry))
                if isinstance(entry_id, int):
                    existing_ids.add(entry_id)
                restored_any = True
            if restored_any:
                if not self._persist_todos():
                    self.todos = previous_todos
                    QMessageBox.warning(
                        self,
                        "撤销失败",
                        "无法将清理的任务写回磁盘，已保留撤销操作，请稍后重试。",
                    )
                    return False
                self.update_list_widget()
            return True

        self._register_or_defer_undo(
            f"已清理 {len(removed_entries)} 条已完成任务",
            _undo_clear,
            defer=defer_undo_toast,
        )
        return len(removed_entries)

    def export_todos_to_file(self, file_path: str | Path) -> int:
        target = Path(file_path)
        resolved_target = target.resolve()
        protected_candidates: list[Path] = [
            _storage.DATA_FILE,
            _storage.DATA_FILE.with_name(f"{_storage.DATA_FILE.name}.bak"),
        ]
        if self._storage_status is not None:
            protected_candidates.append(self._storage_status.data_file)
            if self._storage_status.backup_file is not None:
                protected_candidates.append(self._storage_status.backup_file)
        protected_resolved = {path.resolve() for path in protected_candidates}
        if resolved_target in protected_resolved:
            raise ValueError("不能直接覆盖正在使用的待办数据文件或其备份文件，请另选目标路径。")
        if target.exists():
            for candidate in protected_candidates:
                if not candidate.exists():
                    continue
                try:
                    if target.samefile(candidate):
                        raise ValueError("不能直接覆盖正在使用的待办数据文件或其备份文件，请另选目标路径。")
                except OSError:
                    continue
        payload = {
            "version": APP_VERSION,
            "exportedAt": datetime.now(timezone.utc).isoformat(),
            "todos": copy.deepcopy(self.todos),
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(serialized)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, target)
            temp_path = None
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return len(self.todos)

    def import_todos_from_file(
        self,
        file_path: str | Path,
        *,
        defer_undo_toast: bool = False,
    ) -> int:
        if self._is_storage_read_only():
            self._sync_storage_warning_banner()
            raise RuntimeError("只读恢复模式下无法导入任务，请先恢复可写存储。")
        source = Path(file_path)
        parsed = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            raw_items = parsed.get("todos")
        elif isinstance(parsed, list):
            raw_items = parsed
        else:
            raw_items = None
        if not isinstance(raw_items, list):
            raise ValueError("导入文件必须是任务数组或包含 todos 列表的 JSON 对象。")
        for idx, raw_item in enumerate(raw_items):
            self._validate_imported_todo_item(raw_item, idx)
        normalized = normalize_todo_list(raw_items)
        if not normalized:
            return 0
        previous_len = len(self.todos)
        existing_ids = {
            int(item["id"])
            for item in self.todos
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        }
        next_id = max(existing_ids, default=0) + 1
        imported_ids: set[int] = set()
        for item in normalized:
            for ts_field in ("createdAt", "dueDate", "snoozeUntil"):
                parsed_ts = self._parse_iso_datetime(item.get(ts_field))
                if parsed_ts is not None:
                    item[ts_field] = parsed_ts.isoformat()
            candidate_id = item.get("id")
            if not isinstance(candidate_id, int) or candidate_id <= 0 or candidate_id in existing_ids:
                while next_id in existing_ids:
                    next_id += 1
                item["id"] = next_id
                next_id += 1
            int_id = int(item["id"])
            existing_ids.add(int_id)
            imported_ids.add(int_id)
        self.todos.extend(normalized)
        if not self._persist_todos():
            del self.todos[previous_len:]
            raise RuntimeError("写入待办文件失败，已回滚本次导入。")
        self.update_list_widget()

        def _undo_import() -> bool:
            previous_todos = list(self.todos)
            before_count = len(self.todos)
            self.todos = [
                item
                for item in self.todos
                if not (isinstance(item, dict) and item.get("id") in imported_ids)
            ]
            if len(self.todos) != before_count:
                if not self._persist_todos():
                    self.todos = previous_todos
                    QMessageBox.warning(
                        self,
                        "撤销失败",
                        "无法撤销导入并写回磁盘，已保留撤销操作，请稍后重试。",
                    )
                    return False
                self._remove_notification_tasks(sorted(imported_ids))
                self.update_list_widget()
            return True

        self._register_or_defer_undo(
            f"已导入 {len(normalized)} 条待办",
            _undo_import,
            defer=defer_undo_toast,
        )
        return len(normalized)

    def _prompt_clear_completed_todos(self, dialog: Optional[SettingsDialog] = None) -> None:
        completed_count = sum(
            1 for item in self.todos if isinstance(item, dict) and item.get("completed", False)
        )
        if completed_count <= 0:
            return
        reply = QMessageBox.question(
            dialog or self,
            "清理已完成任务",
            f"确定要删除全部 {completed_count} 条已完成任务吗？（可在 5 秒内撤销）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = self.clear_completed_todos(defer_undo_toast=dialog is not None)
        except Exception as exc:  # noqa: BLE001
            self._deferred_undo_toast = None
            QMessageBox.warning(dialog or self, "清理失败", str(exc))
            return
        if dialog is not None and removed > 0:
            dialog.clear_completed_button.setText("清理已完成 (0)")
            dialog.clear_completed_button.setEnabled(False)
            dialog.accept()

    def _prompt_export_todos(self, dialog: Optional[SettingsDialog] = None) -> None:
        default_name = f"todolist-backup-{datetime.now().strftime('%Y%m%d')}.json"
        file_path, _selected_filter = QFileDialog.getSaveFileName(
            dialog or self,
            "导出待办数据",
            default_name,
            "JSON 文件 (*.json);;所有文件 (*.*)",
        )
        if not file_path:
            return
        try:
            count = self.export_todos_to_file(file_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(dialog or self, "导出失败", f"导出数据失败：{exc}")
            return
        QMessageBox.information(dialog or self, "导出成功", f"已导出 {count} 条待办至：\n{file_path}")

    def _prompt_import_todos(self, dialog: Optional[SettingsDialog] = None) -> None:
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            dialog or self,
            "导入待办数据",
            "",
            "JSON 文件 (*.json);;所有文件 (*.*)",
        )
        if not file_path:
            return
        try:
            count = self.import_todos_from_file(file_path, defer_undo_toast=dialog is not None)
        except Exception as exc:  # noqa: BLE001
            self._deferred_undo_toast = None
            QMessageBox.warning(dialog or self, "导入失败", f"导入数据失败：{exc}")
            return
        if dialog is not None:
            completed_count = sum(
                1 for item in self.todos if isinstance(item, dict) and item.get("completed", False)
            )
            dialog.clear_completed_button.setText(f"清理已完成 ({completed_count})")
            dialog.clear_completed_button.setEnabled(completed_count > 0)
        QMessageBox.information(dialog or self, "导入完成", f"成功导入 {count} 条待办。")
        if dialog is not None and count > 0:
            dialog.accept()

    def open_settings_dialog(self) -> int:
        autostart_supported = is_autostart_supported()
        autostart_enabled = is_autostart_enabled() if autostart_supported else False
        completed_count = sum(
            1 for item in self.todos if isinstance(item, dict) and item.get("completed", False)
        )
        dialog = SettingsDialog(
            theme_preference=self.theme_manager.preference,
            sound_enabled=self._sound_enabled,
            dnd_enabled=self.is_dnd_active(),
            dnd_status_text=self.dnd_status_text(),
            autostart_supported=autostart_supported,
            autostart_enabled=autostart_enabled,
            completed_count=completed_count,
            parent=self,
        )
        self._settings_dialog = dialog
        self._deferred_undo_toast = None
        dialog.theme_preference_changed.connect(self.set_theme_preference)
        dialog.sound_enabled_changed.connect(self.set_sound_enabled)

        def _on_dnd_toggled(enabled: bool) -> None:
            self.set_dnd_enabled(enabled)

        def _on_dnd_1h() -> None:
            self.enable_dnd_for_one_hour()

        dialog.dnd_toggled.connect(_on_dnd_toggled)
        dialog.dnd_one_hour_requested.connect(_on_dnd_1h)
        dialog.autostart_toggled.connect(
            lambda enabled: self._set_autostart_enabled(enabled, dialog)
        )
        dialog.clear_completed_requested.connect(
            lambda: self._prompt_clear_completed_todos(dialog)
        )
        dialog.export_todos_requested.connect(lambda: self._prompt_export_todos(dialog))
        dialog.import_todos_requested.connect(lambda: self._prompt_import_todos(dialog))
        dialog.open_storage_dir_requested.connect(self._open_storage_directory)
        try:
            result = dialog.exec()
        finally:
            self._settings_dialog = None
            dialog.deleteLater()
        self._flush_deferred_undo_toast()
        return result

    # --- 状态保存 ---
    def save_geometry_and_state(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("filterOption", self.filter_combo.currentText())
        self.settings.setValue("sortOption", self.sort_combo.currentText())
        self.settings.setValue("windowAlwaysOnTop", self._always_on_top)
        self.settings.setValue("themePreference", self.theme_manager.preference.value)
        self.settings.setValue("soundEnabled", self._sound_enabled)
        self.settings.setValue("dndEnabled", self._dnd_enabled)
        self.settings.setValue(
            "dndUntilUtc",
            self._dnd_until_utc.isoformat() if self._dnd_until_utc is not None else "",
        )
        self.settings.sync()

    def restore_geometry_and_state(self) -> None:
        geom_bytes = self.settings.value("geometry")
        state_bytes = self.settings.value("windowState")
        saved_filter = self.settings.value("filterOption")
        saved_sort = self.settings.value("sortOption")
        saved_pin = self.settings.value("windowAlwaysOnTop")
        saved_theme = self.settings.value("themePreference")
        saved_sound = self.settings.value("soundEnabled")
        saved_dnd = self.settings.value("dndEnabled")
        saved_dnd_until = self.settings.value("dndUntilUtc")
        self._restoring_view_options = True
        try:
            if isinstance(saved_filter, str) and self.filter_combo.findText(saved_filter) >= 0:
                self.filter_combo.setCurrentText(saved_filter)
            if isinstance(saved_sort, str) and self.sort_combo.findText(saved_sort) >= 0:
                self.sort_combo.setCurrentText(saved_sort)
        finally:
            self._restoring_view_options = False
        pinned = self._coerce_bool_setting(saved_pin, False)
        self._apply_pin_state(pinned, persist=False)
        if isinstance(saved_theme, str) and saved_theme.strip():
            self.theme_manager.set_preference(ThemePreference.coerce(saved_theme))
        self._sound_enabled = self._coerce_bool_setting(saved_sound, True)
        self._dnd_enabled = self._coerce_bool_setting(saved_dnd, False)
        self._dnd_until_utc = self._parse_iso_datetime(saved_dnd_until)
        if (
            self._dnd_enabled
            and self._dnd_until_utc is not None
            and self._dnd_until_utc <= datetime.now(timezone.utc)
        ):
            self._dnd_enabled = False
            self._dnd_until_utc = None
        self._sync_dnd_ui()
        screen = QApplication.primaryScreen()
        target_width, target_height = 320, 640
        if screen:
            available = screen.availableGeometry()
            default_width = min(target_width, available.width())
            default_height = min(target_height, available.height())
        else:
            default_width, default_height = target_width, target_height
        default_size = QSize(
            max(default_width, self.minimumWidth()),
            max(default_height, self.minimumHeight()),
        )
        restored_geom = False
        if isinstance(geom_bytes, QByteArray) and not geom_bytes.isEmpty():
            restored_geom = bool(self.restoreGeometry(geom_bytes))
            if not restored_geom:
                print("警告: 恢复窗口几何位置失败。")
        if not restored_geom:
            self.resize(default_size)
            self._center_window()
        if isinstance(state_bytes, QByteArray) and not state_bytes.isEmpty():
            if not self.restoreState(state_bytes):
                print("警告: 恢复窗口状态失败。使用默认状态。")
                self.showNormal()
        else:
            self.showNormal()
        self._ensure_window_on_screen()

    def _center_window(self) -> None:
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def _ensure_window_on_screen(self) -> None:
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        if not screen:
            return
        screen_geom = screen.availableGeometry()
        window_geom = self.frameGeometry()
        if not screen_geom.intersects(window_geom) or window_geom.width() < self.minimumWidth() or window_geom.height() < self.minimumHeight():
            dw = min(max(self.minimumSizeHint().width(), 320), int(screen_geom.width() * 0.85))
            dh = min(max(self.minimumSizeHint().height(), 640), int(screen_geom.height() * 0.85))
            self.resize(QSize(dw, dh))
            self._center_window()
            if self.isMinimized() or not self.isVisible():
                self.showNormal()

    def _update_empty_placeholder_geometry(self) -> None:
        if (
            self._quitting_app
            or not self._empty_placeholder_item
            or not self._empty_placeholder_widget
        ):
            return
        try:
            viewport = self.list_widget.viewport() if self.list_widget else None
            viewport_size = viewport.size() if viewport else self.list_widget.size()
        except RuntimeError:
            return
        width = max(viewport_size.width() - 10, 200)
        vertical_spacing = self.list_widget.spacing() * 2
        height = max(viewport_size.height() - vertical_spacing, 160)
        self._empty_placeholder_item.setSizeHint(QSize(width, height))
        self._empty_placeholder_widget.setMinimumSize(width, height)

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        if (
            hasattr(self, "quick_add_input")
            and watched is self.quick_add_input
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            open_full = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._submit_quick_add(open_full_dialog=open_full)
            return True
        if (
            hasattr(self, "search_input")
            and watched is self.search_input
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self._handle_escape_shortcut()
            return True
        if (
            hasattr(self, "list_widget")
            and watched is self.list_widget.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            self._sync_todo_card_sizes()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_empty_placeholder_geometry()
        self._sync_todo_card_sizes()

    def showEvent(self, event: QEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_todo_card_sizes()
        QTimer.singleShot(0, self._update_empty_placeholder_geometry)

    # --- 关闭流程 ---
    def closeEvent(self, event: QEvent) -> None:  # noqa: N802
        self.save_geometry_and_state()

        tray_icon = getattr(self, "tray_icon", None)
        if tray_icon and tray_icon.isVisible() and not self._quitting_app:
            self._hide_notification_dialog()
            self.hide()
            event.ignore()
        else:
            self._close_notification_dialog()
            if not self._quitting_app:
                self.quit_application(from_close_event=True)
            event.accept()

    def quit_application(self, from_close_event: bool = False) -> None:
        if getattr(self, "_quit_app_called_flag", False) and not from_close_event:
            return
        self._quit_app_called_flag = True
        self._quitting_app = True
        self._close_notification_dialog()
        if hasattr(self, "master_timer"):
            self.master_timer.stop()
        save_todos(self.todos)
        if hasattr(self, "reminder_sound"):
            self.reminder_sound.stop()
        if hasattr(self, "due_sound"):
            self.due_sound.stop()
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
        QApplication.instance().quit()


__all__ = ["ModernTodoAppWindow"]
