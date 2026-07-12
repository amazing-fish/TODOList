"""主窗口实现。"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import quote
from textwrap import dedent

from PySide6.QtCore import QByteArray, QEvent, QSettings, QTimer, Qt, QSize, Slot
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    APP_ICON_PATH,
    APP_NAME,
    APP_VERSION,
    ADD_ICON_PATH,
    DUE_SOUND_PATH,
    REMINDER_SOUND_PATH,
)
from .dialogs import NotificationDialog, TaskEditDialog
from .scheduling import build_edit_update_fields, build_snooze_update_fields
from .storage import load_todos, save_todos
from .utils import get_icon, play_sound_effect
from .widgets import TodoItemWidget
from .theme import ThemeColors, get_theme_manager


class ModernTodoAppWindow(QMainWindow):
    """现代风格的待办事项管理主窗口。"""

    def __init__(self):
        super().__init__()
        self.todos: List[Dict] = load_todos()
        self._notification_dialog: Optional[NotificationDialog] = None
        self.settings = QSettings("MyProductiveApp", APP_NAME)
        self._quitting_app = False

        self.theme_manager = get_theme_manager()
        self._palette: ThemeColors = self.theme_manager.current_palette
        self.theme_manager.theme_changed.connect(self._on_theme_changed)

        self.reminder_sound = QSoundEffect(self)
        self.due_sound = QSoundEffect(self)
        self.reminder_sound.setVolume(0.7)
        self.due_sound.setVolume(0.8)

        self._add_task_dialog: Optional[TaskEditDialog] = None
        self._empty_placeholder_item: Optional[QListWidgetItem] = None
        self._empty_placeholder_widget: Optional[QWidget] = None
        self._empty_placeholder_label: Optional[QLabel] = None

        self._build_ui()
        self._create_tray_icon()
        self.update_list_widget()

        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.tick_update)
        self.master_timer.start(1000)
        self.restore_geometry_and_state()

        self._last_minimize_to_tray_notified = False
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
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        self.filter_label = QLabel("筛选:")
        controls_layout.addWidget(self.filter_label)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "未完成", "已完成", "今天到期", "高优先级"])
        self.filter_combo.currentTextChanged.connect(self.update_list_widget)
        controls_layout.addWidget(self.filter_combo)

        self.sort_label = QLabel("排序:")
        controls_layout.addWidget(self.sort_label)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(
            ["创建时间 (新->旧)", "创建时间 (旧->新)", "截止日期 (近->远)", "截止日期 (远->近)", "优先级 (高->低)"]
        )
        self.sort_combo.currentTextChanged.connect(self.update_list_widget)
        controls_layout.addWidget(self.sort_combo)

        controls_layout.addStretch(1)

        self.add_button = QPushButton()
        self.add_button.setToolTip("添加新任务")
        self.add_button.setFixedSize(36, 36)
        self.add_button.setIcon(get_icon(ADD_ICON_PATH, "+"))
        self.add_button.setIconSize(QSize(18, 18))
        self.add_button.setAccessibleName("添加任务")
        self.add_button.clicked.connect(self.show_add_task_dialog)
        main_layout.addLayout(controls_layout)

        list_header_layout = QHBoxLayout()
        self.list_label = QLabel("待办列表")
        list_header_layout.addWidget(self.list_label)
        list_header_layout.addStretch(1)
        list_header_layout.addWidget(self.add_button)
        main_layout.addLayout(list_header_layout)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            """
            QListWidget { background-color: transparent; border: none; padding: 0px; }
            QListWidget::item { border: none; margin: 0px; padding: 0px; }
            """
        )
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(self.list_widget, 1)
        self._apply_global_font()
        self._apply_palette(self._palette)

    def _apply_global_font(self) -> None:
        font_family = "Segoe UI"
        if sys.platform == "darwin":
            font_family = "San Francisco"
        elif sys.platform.startswith("linux"):
            font_family = "Noto Sans"

        from PySide6.QtGui import QFont

        test_font = QFont(font_family, 10)
        if QFont(test_font).family() == font_family:
            QApplication.setFont(test_font)
        else:
            QApplication.setFont(QFont("Arial", 10))

    def _apply_palette(self, palette: ThemeColors) -> None:
        """根据主题配色刷新窗口视觉样式。"""

        self._palette = palette
        self.setStyleSheet(f"QMainWindow {{ background-color: {palette.background}; }}")
        self.add_button.setStyleSheet(
            f"""
            QPushButton {{
                 background-color: {palette.accent}; color: {palette.inverse_text};
                 border: none; border-radius: 18px; font-weight: bold; font-size: 16pt;
            }}
            QPushButton:hover {{ background-color: {palette.accent_hover}; }}
            """
        )
        self.list_label.setStyleSheet(
            f"font-size: 13pt; font-weight:bold; color: {palette.list_label}; margin-top: 8px; margin-bottom: 3px;"
        )
        self.filter_label.setStyleSheet(
            f"color: {palette.text_primary}; font-size: 10pt; background-color: transparent;"
        )
        self.sort_label.setStyleSheet(
            f"color: {palette.text_primary}; font-size: 10pt; background-color: transparent;"
        )
        self._apply_combo_palette(self.filter_combo, palette)
        self._apply_combo_palette(self.sort_combo, palette)
        if self._empty_placeholder_label is not None:
            self._empty_placeholder_label.setStyleSheet(
                f"color: {palette.text_secondary}; font-style: italic; font-size: 12pt; background-color: transparent;"
            )

    def _build_combo_arrow_uri(self, stroke_color: str) -> str:
        """根据主题颜色构建下拉箭头 SVG 的 data URI。"""

        svg = (
            "<svg width=\"12\" height=\"8\" viewBox=\"0 0 12 8\" xmlns=\"http://www.w3.org/2000/svg\">"
            f"<path d=\"M1.5 2.25L6 6.75L10.5 2.25\" stroke=\"{stroke_color}\" stroke-width=\"1.5\" "
            "stroke-linecap=\"round\" stroke-linejoin=\"round\"/>"
            "</svg>"
        )
        return f"data:image/svg+xml,{quote(svg)}"

    def _apply_combo_palette(self, combo: Optional[QComboBox], palette: ThemeColors) -> None:
        """为筛选和排序下拉框应用主题色样式。"""

        if combo is None:
            return

        combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)

        arrow_normal = self._build_combo_arrow_uri(palette.text_primary)
        arrow_disabled = self._build_combo_arrow_uri(palette.text_secondary)

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
                    image: url('{arrow_normal}');
                    width: 9px;
                    height: 5px;
                }}
                QComboBox::down-arrow:disabled {{
                    image: url('{arrow_disabled}');
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

        self._update_combo_compact_width(combo)

    def _update_combo_compact_width(self, combo: Optional[QComboBox]) -> None:
        """根据内容与样式计算组合框宽度，避免文本被截断或出现空白区。"""

        if combo is None:
            return

        if combo.count() == 0:
            return

        metrics = combo.fontMetrics()
        max_text = max(
            (combo.itemText(index) for index in range(combo.count())),
            key=metrics.horizontalAdvance,
        )
        text_width = metrics.horizontalAdvance(max_text)
        option = QStyleOptionComboBox()
        option.initFrom(combo)
        option.currentText = max_text
        option.fontMetrics = metrics
        size = combo.style().sizeFromContents(QStyle.CT_ComboBox, option, QSize(text_width, 0), combo)
        combo.setFixedWidth(size.width() + 2)


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

    # --- 主循环刷新 ---
    def tick_update(self) -> None:
        now_utc = datetime.now(timezone.utc)
        items_changed = False
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
                        items_changed = True
                except ValueError:
                    original_ref["snoozeUntil"] = None
                    items_changed = True
            notification_request = self._check_for_notification(original_ref, now_utc)
            if notification_request:
                notification_requests.append(notification_request)
                items_changed = True

        todos_by_id = {todo.get("id"): todo for todo in self.todos}
        for index in range(self.list_widget.count()):
            list_item = self.list_widget.item(index)
            if not list_item:
                continue
            item_widget = self.list_widget.itemWidget(list_item)
            if not isinstance(item_widget, TodoItemWidget):
                continue
            original_ref = todos_by_id.get(item_widget.todo_item.get("id"))
            if original_ref:
                item_widget.todo_item.update(original_ref)
            item_widget.update_timer_display(now_utc)

        if items_changed:
            save_todos(self.todos)
            self.update_list_widget()
        if notification_requests:
            self._show_notification_batch(notification_requests)

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
        if any(is_due for _, is_due in requests):
            play_sound_effect(self.due_sound, DUE_SOUND_PATH)
        else:
            play_sound_effect(self.reminder_sound, REMINDER_SOUND_PATH)

        self._ensure_window_visible_for_notification()
        dialog = self._notification_dialog
        if dialog is None:
            dialog = NotificationDialog(requests, self)
            self._notification_dialog = dialog
            dialog.complete_requested.connect(self._handle_notification_complete)
            dialog.snooze_requested.connect(self._handle_notification_snooze)
            dialog.finished.connect(self._on_notification_dialog_finished)
            dialog.show()
        else:
            dialog.add_or_update_tasks(requests)
        dialog.raise_()
        dialog.activateWindow()

    def _on_notification_dialog_finished(self, _result: int) -> None:
        if self._notification_dialog is self.sender():
            self._notification_dialog = None

    def _handle_notification_complete(self, todo_ids: list[int]) -> None:
        requested_ids = {int(todo_id) for todo_id in todo_ids}
        changed = False
        for todo in self.todos:
            if todo.get("id") not in requested_ids or todo.get("completed", False):
                continue
            todo.update(
                {
                    "completed": True,
                    "snoozeUntil": None,
                    "notifiedForReminder": True,
                    "notifiedForDue": True,
                }
            )
            changed = True

        self._remove_notification_tasks(list(requested_ids))
        if changed:
            save_todos(self.todos)
            self.update_list_widget()

    def _handle_notification_snooze(
        self, todo_ids: list[int], snooze_duration: timedelta
    ) -> None:
        requested_ids = {int(todo_id) for todo_id in todo_ids}
        changed = False
        for todo in self.todos:
            if todo.get("id") not in requested_ids or todo.get("completed", False):
                continue
            todo.update(build_snooze_update_fields(todo, snooze_duration))
            changed = True

        self._remove_notification_tasks(list(requested_ids))
        if changed:
            save_todos(self.todos)
            self.update_list_widget()

    def _remove_notification_tasks(self, todo_ids: list[int]) -> None:
        if self._notification_dialog is not None:
            self._notification_dialog.remove_tasks(todo_ids)

    def _remove_notification_task(self, todo_id: object) -> None:
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is not None:
            self._remove_notification_tasks([normalized_id])

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
        self._last_minimize_to_tray_notified = False

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
        if not self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
            return

        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.show()

    # --- 任务操作 ---
    def show_add_task_dialog(self) -> None:
        if self._add_task_dialog and self._add_task_dialog.isVisible():
            if self._add_task_dialog.isMinimized():
                self._add_task_dialog.showNormal()
            self._add_task_dialog.raise_()
            self._add_task_dialog.activateWindow()
            return

        dialog = TaskEditDialog(parent=self)
        self._add_task_dialog = dialog
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_data = dialog.get_task_data()

                current_ids = [t["id"] for t in self.todos if isinstance(t.get("id"), int)]
                max_id = max(current_ids) if current_ids else 0
                new_id_time = int(datetime.now(timezone.utc).timestamp() * 1000)
                new_id = max(new_id_time, max_id + 1)
                existing_ids = set(current_ids)
                while new_id in existing_ids:
                    new_id += 1

                new_todo = {
                    "id": new_id,
                    "text": new_data["text"],
                    "priority": new_data["priority"],
                    "dueDate": new_data["dueDate"],
                    "reminderOffset": new_data["reminderOffset"],
                    "completed": False,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "snoozeUntil": None,
                    "notifiedForReminder": False,
                    "notifiedForDue": False,
                    "lastNotifiedAt": None,
                }
                self.todos.append(new_todo)
                save_todos(self.todos)
                self.update_list_widget()
        finally:
            if self._add_task_dialog is dialog:
                self._add_task_dialog = None

    def _normalize_todo_id(self, raw_id: object) -> Optional[int]:
        """尝试将传入的任务 ID 规范化为 Python int。"""
        try:
            return int(raw_id)
        except (TypeError, ValueError):
            print(f"警告: 收到无法识别的任务ID: {raw_id!r}")
            return None

    @Slot(object)
    def handle_edit_request(self, todo_id: object) -> None:
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is None:
            QMessageBox.warning(self, "错误", "收到无效的任务标识，无法编辑。")
            return

        todo_to_edit = next((t for t in self.todos if t.get("id") == normalized_id), None)
        if not todo_to_edit:
            QMessageBox.warning(self, "错误", "无法找到要编辑的任务。")
            return

        dialog = TaskEditDialog(todo_item=todo_to_edit, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_data = dialog.get_task_data()
            for index, todo in enumerate(self.todos):
                if todo["id"] == normalized_id:
                    self.todos[index].update(build_edit_update_fields(todo, updated_data))
                    self._remove_notification_task(normalized_id)
                    break

            save_todos(self.todos)
            self.update_list_widget()

    @Slot(object)
    def handle_delete_request(self, todo_id: object) -> None:
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is None:
            QMessageBox.warning(self, "错误", "收到无效的任务标识，无法删除。")
            return

        todo_to_delete = next((t for t in self.todos if t.get("id") == normalized_id), None)
        item_text = (
            f"待办事项 \"{todo_to_delete['text'][:30]}{'...' if len(todo_to_delete['text']) > 30 else ''}\""
            if todo_to_delete
            else "这个待办事项"
        )
        if (
            QMessageBox.question(
                self,
                "确认删除",
                f"您确定要删除 {item_text} 吗？此操作无法撤销。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self._remove_notification_task(normalized_id)
            original_len = len(self.todos)
            self.todos = [t for t in self.todos if t.get("id") != normalized_id]
            if len(self.todos) < original_len:
                save_todos(self.todos)
                self.update_list_widget()
            else:
                print(f"警告: 删除任务时未找到ID {normalized_id}。")

    @Slot(object)
    def handle_toggle_complete_request(self, todo_id: object) -> None:
        self.toggle_complete_todo(todo_id)

    def toggle_complete_todo(self, todo_id: object, called_from_notification: bool = False) -> None:
        normalized_id = self._normalize_todo_id(todo_id)
        if normalized_id is None:
            print(f"警告: 尝试切换任务完成状态时收到无效ID: {todo_id!r}")
            return

        changed = False
        for index, todo in enumerate(self.todos):
            if todo.get("id") == normalized_id:
                is_now_completed = not todo.get("completed", False)
                self.todos[index]["completed"] = is_now_completed
                if is_now_completed:
                    self.todos[index].update(
                        {
                            "snoozeUntil": None,
                            "notifiedForReminder": True,
                            "notifiedForDue": True,
                        }
                    )
                    self._remove_notification_task(normalized_id)
                else:
                    self.todos[index].update(
                        {
                            "notifiedForReminder": False,
                            "notifiedForDue": False,
                            "lastNotifiedAt": None,
                        }
                    )
                changed = True
                break

        if changed:
            save_todos(self.todos)
            self.update_list_widget()
        else:
            print(f"警告: 切换ID {normalized_id} 任务完成状态时未找到。")

    # --- 列表刷新 ---
    def update_list_widget(self) -> None:
        self.list_widget.clear()
        if not isinstance(self.todos, list):
            self.todos = []

        working_copy = [item.copy() for item in self.todos if isinstance(item, dict) and "id" in item]
        processed = self._sort_todos(self._filter_todos(working_copy))
        if not processed:
            self._show_empty_list_message()
            return

        self._empty_placeholder_item = None
        self._empty_placeholder_widget = None
        self._empty_placeholder_label = None

        current_time_utc = datetime.now(timezone.utc)
        for todo_data in processed:
            list_item = QListWidgetItem(self.list_widget)
            item_widget = TodoItemWidget(todo_data.copy(), palette=self._palette)
            item_widget.request_edit.connect(self.handle_edit_request)
            item_widget.request_delete.connect(self.handle_delete_request)
            item_widget.request_toggle_complete.connect(self.handle_toggle_complete_request)
            list_item.setSizeHint(item_widget.sizeHint())
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, item_widget)
            item_widget.update_timer_display(current_time_utc)

    def _show_empty_list_message(self) -> None:
        self.list_widget.clear()
        empty_item = QListWidgetItem(self.list_widget)
        empty_container = QWidget()
        container_layout = QVBoxLayout(empty_container)
        container_layout.setContentsMargins(0, 40, 0, 40)
        container_layout.setSpacing(0)
        container_layout.addStretch()

        empty_label = QLabel("🎉 暂无待办事项！")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        container_layout.addWidget(empty_label, alignment=Qt.AlignmentFlag.AlignCenter)
        container_layout.addStretch()

        self.list_widget.addItem(empty_item)
        self.list_widget.setItemWidget(empty_item, empty_container)

        self._empty_placeholder_item = empty_item
        self._empty_placeholder_widget = empty_container
        self._empty_placeholder_label = empty_label
        self._apply_palette(self._palette)
        self._update_empty_placeholder_geometry()
        QTimer.singleShot(0, self._update_empty_placeholder_geometry)

    def _filter_todos(self, todos_list: List[dict]) -> List[dict]:
        filter_text = self.filter_combo.currentText()
        if filter_text == "全部":
            return todos_list

        today_local = datetime.now().astimezone().date()
        filtered: List[dict] = []
        for todo in todos_list:
            add = False
            if filter_text == "未完成":
                add = not todo.get("completed", False)
            elif filter_text == "已完成":
                add = todo.get("completed", False)
            elif filter_text == "今天到期" and not todo.get("completed", False) and todo.get("dueDate"):
                try:
                    if datetime.fromisoformat(todo["dueDate"].replace("Z", "+00:00")).astimezone().date() == today_local:
                        add = True
                except ValueError:
                    pass
            elif filter_text == "高优先级" and not todo.get("completed", False) and todo.get("priority") == "高":
                add = True
            if add:
                filtered.append(todo)
        return filtered

    def _sort_todos(self, todos_list: List[dict]) -> List[dict]:
        sort_key = self.sort_combo.currentText()

        def get_due(todo: dict, future_extreme: bool = True) -> datetime:
            due_str = todo.get("dueDate")
            if due_str:
                try:
                    return datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                except ValueError:
                    pass
            extreme_date = datetime.max if future_extreme else datetime.min
            return extreme_date.replace(tzinfo=timezone.utc)

        priority_value = lambda p: {"高": 0, "中": 1, "低": 2}.get(p, 3)

        if sort_key == "创建时间 (新->旧)":
            return sorted(
                todos_list,
                key=lambda t: datetime.fromisoformat(t["createdAt"].replace("Z", "+00:00")),
                reverse=True,
            )
        if sort_key == "创建时间 (旧->新)":
            return sorted(
                todos_list,
                key=lambda t: datetime.fromisoformat(t["createdAt"].replace("Z", "+00:00")),
            )
        if sort_key == "截止日期 (近->远)":
            return sorted(
                todos_list,
                key=lambda t: (t.get("completed", False), get_due(t, True)),
            )
        if sort_key == "截止日期 (远->近)":
            return sorted(
                todos_list,
                key=lambda t: (t.get("completed", False), get_due(t, True)),
                reverse=True,
            )
        if sort_key == "优先级 (高->低)":
            return sorted(
                todos_list,
                key=lambda t: (
                    t.get("completed", False),
                    priority_value(t.get("priority", "中")),
                    get_due(t, True),
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
        tray_menu.addAction("退出应用", self.quit_application)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
        self.tray_icon.show()

    def quick_add_from_tray(self) -> None:
        if self.isHidden() or self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        self._last_minimize_to_tray_notified = False
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

    def _minimize_to_tray(self) -> None:
        if self._quitting_app:
            return
        self.hide()
        tray_icon = getattr(self, "tray_icon", None)
        if not self._last_minimize_to_tray_notified and tray_icon and tray_icon.isVisible():
            tray_icon.showMessage(
                APP_NAME,
                "应用已最小化到系统托盘。",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            self._last_minimize_to_tray_notified = True

    def _on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window_visibility()

    def toggle_window_visibility(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()
        if self.isVisible():
            self._last_minimize_to_tray_notified = False

    # --- 状态保存 ---
    def save_geometry_and_state(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.sync()

    def restore_geometry_and_state(self) -> None:
        geom_bytes = self.settings.value("geometry")
        state_bytes = self.settings.value("windowState")
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
        if not self._empty_placeholder_item or not self._empty_placeholder_widget:
            return

        viewport = self.list_widget.viewport() if self.list_widget else None
        viewport_size = viewport.size() if viewport else self.list_widget.size()
        width = max(viewport_size.width() - 10, 200)
        height = max(viewport_size.height(), 160)
        self._empty_placeholder_item.setSizeHint(QSize(width, height))
        self._empty_placeholder_widget.setMinimumSize(width, height)

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_empty_placeholder_geometry()

    def showEvent(self, event: QEvent) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._update_empty_placeholder_geometry)

    # --- 关闭流程 ---
    def closeEvent(self, event: QEvent) -> None:  # noqa: N802
        if self._notification_dialog is not None:
            self._notification_dialog.close()
            self._notification_dialog = None

        self.save_geometry_and_state()

        tray_icon = getattr(self, "tray_icon", None)
        if tray_icon and tray_icon.isVisible() and not self._quitting_app:
            self.hide()
            event.ignore()
            tray_icon.showMessage(
                APP_NAME,
                "应用已最小化到系统托盘。",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            self._last_minimize_to_tray_notified = True
        else:
            if not self._quitting_app:
                self.quit_application(from_close_event=True)
            event.accept()

    def quit_application(self, from_close_event: bool = False) -> None:
        if getattr(self, "_quit_app_called_flag", False) and not from_close_event:
            return
        self._quit_app_called_flag = True
        self._quitting_app = True
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
