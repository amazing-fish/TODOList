"""主窗口实现。"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

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
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    APP_ICON_PATH,
    APP_NAME,
    APP_VERSION,
    ADD_ICON_PATH,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_BACKGROUND,
    COLOR_TEXT_SECONDARY,
    DUE_SOUND_PATH,
    REMINDER_SOUND_PATH,
)
from .dialogs import NotificationDialog, TaskEditDialog
from .storage import load_todos, save_todos
from .utils import get_icon, play_sound_effect
from .widgets import TodoItemWidget


class ModernTodoAppWindow(QMainWindow):
    """现代风格的待办事项管理主窗口。"""

    def __init__(self):
        super().__init__()
        self.todos: List[Dict] = load_todos()
        self.active_notifications: Dict[int, QDialog] = {}
        self.settings = QSettings("MyProductiveApp", APP_NAME)
        self._quitting_app = False

        self.reminder_sound = QSoundEffect(self)
        self.due_sound = QSoundEffect(self)
        self.reminder_sound.setVolume(0.7)
        self.due_sound.setVolume(0.8)

        self._build_ui()
        self._create_tray_icon()
        self.update_list_widget()

        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.tick_update)
        self.master_timer.start(1000)
        self.restore_geometry_and_state()

    # --- UI 初始化 ---
    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} - v{APP_VERSION}")
        self.setWindowIcon(get_icon(APP_ICON_PATH, "T"))
        self.setMinimumSize(320, 400)
        self.setStyleSheet(f"QMainWindow {{ background-color: {COLOR_BACKGROUND}; }}")

        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        filter_label = QLabel("筛选:")
        controls_layout.addWidget(filter_label)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "未完成", "已完成", "今天到期", "高优先级"])
        self.filter_combo.currentTextChanged.connect(self.update_list_widget)
        controls_layout.addWidget(self.filter_combo, 1)

        sort_label = QLabel("排序:")
        controls_layout.addWidget(sort_label)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(
            ["创建时间 (新->旧)", "创建时间 (旧->新)", "截止日期 (近->远)", "截止日期 (远->近)", "优先级 (高->低)"]
        )
        self.sort_combo.currentTextChanged.connect(self.update_list_widget)
        controls_layout.addWidget(self.sort_combo, 2)

        self.add_button = QPushButton()
        self.add_button.setToolTip("添加新任务")
        self.add_button.setFixedSize(36, 36)
        self.add_button.setStyleSheet(
            f"""
            QPushButton {{
                 background-color: {COLOR_ACCENT}; color: white;
                 border: none; border-radius: 18px; font-weight: bold; font-size: 16pt;
            }}
            QPushButton:hover {{ background-color: {COLOR_ACCENT_HOVER}; }}
            """
        )
        self.add_button.setIcon(get_icon(ADD_ICON_PATH, "+"))
        self.add_button.setIconSize(QSize(18, 18))
        self.add_button.setAccessibleName("添加任务")
        self.add_button.clicked.connect(self.show_add_task_dialog)
        controls_layout.addWidget(self.add_button)
        main_layout.addLayout(controls_layout)

        list_label = QLabel("待办列表")
        list_label.setStyleSheet(
            "font-size: 13pt; font-weight:bold; color: #1A237E; margin-top: 8px; margin-bottom: 3px;"
        )
        main_layout.addWidget(list_label)

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

    # --- 主循环刷新 ---
    def tick_update(self) -> None:
        now_utc = datetime.now(timezone.utc)
        items_changed = False
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            if not list_item:
                continue
            item_widget = self.list_widget.itemWidget(list_item)
            if not isinstance(item_widget, TodoItemWidget):
                continue

            todo = item_widget.todo_item
            original_ref = next((t for t in self.todos if t["id"] == todo["id"]), None)
            if not original_ref:
                continue

            snooze_updated = False
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
                        snooze_updated = True
                        items_changed = True
                except ValueError:
                    original_ref["snoozeUntil"] = None
                    snooze_updated = True
                    items_changed = True

            if snooze_updated:
                todo.update(
                    {
                        "snoozeUntil": original_ref["snoozeUntil"],
                        "notifiedForReminder": original_ref["notifiedForReminder"],
                        "notifiedForDue": original_ref["notifiedForDue"],
                    }
                )

            item_widget.update_timer_display(now_utc)
            self._check_for_notification(original_ref, now_utc)

        if items_changed:
            save_todos(self.todos)
            self.update_list_widget()

    # --- 通知逻辑 ---
    def _check_for_notification(self, todo: dict, current_time_utc: datetime) -> None:
        if todo.get("completed"):
            if todo["id"] in self.active_notifications:
                self.active_notifications.pop(todo["id"]).close()
            return

        due_date_str = todo.get("dueDate")
        if not due_date_str:
            return

        try:
            due_date_dt = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        except ValueError:
            print(f"错误: 任务ID {todo.get('id', '未知')} 截止日期格式无效: {due_date_str}")
            return

        snooze_until = todo.get("snoozeUntil")
        if snooze_until:
            try:
                if datetime.fromisoformat(snooze_until.replace("Z", "+00:00")) > current_time_utc:
                    return
            except ValueError:
                pass

        reminder_offset_sec = todo.get("reminderOffset", 0)
        notification_triggered = False
        if reminder_offset_sec >= 0:
            reminder_time_dt = due_date_dt - timedelta(seconds=reminder_offset_sec)
            if (
                reminder_time_dt <= current_time_utc
                and due_date_dt > current_time_utc
                and not todo.get("notifiedForReminder", False)
            ):
                self._show_notification_dialog(todo, is_due_notification=False)
                todo["notifiedForReminder"] = True
                todo["lastNotifiedAt"] = current_time_utc.isoformat()
                notification_triggered = True

        if due_date_dt <= current_time_utc and not todo.get("notifiedForDue", False):
            self._show_notification_dialog(todo, is_due_notification=True)
            todo["notifiedForDue"] = True
            if not todo.get("notifiedForReminder"):
                todo["notifiedForReminder"] = True
            todo["lastNotifiedAt"] = current_time_utc.isoformat()
            notification_triggered = True

        if notification_triggered:
            save_todos(self.todos)

    def _show_notification_dialog(self, todo_item: dict, is_due_notification: bool) -> None:
        if todo_item["id"] in self.active_notifications:
            dialog = self.active_notifications[todo_item["id"]]
            dialog.raise_()
            dialog.activateWindow()
            return

        if is_due_notification:
            play_sound_effect(self.due_sound, DUE_SOUND_PATH)
        else:
            play_sound_effect(self.reminder_sound, REMINDER_SOUND_PATH)

        dialog = NotificationDialog(todo_item, self)
        self.active_notifications[todo_item["id"]] = dialog
        dialog.raise_()
        dialog.activateWindow()
        result = dialog.exec()
        self.active_notifications.pop(todo_item["id"], None)

        current_ref = next((t for t in self.todos if t["id"] == todo_item["id"]), None)
        if not current_ref:
            print(f"警告: 通知对话框关闭后，任务ID {todo_item['id']} 未在主列表中找到。")
            return

        item_changed = False
        if result == QDialog.DialogCode.Accepted:
            self.toggle_complete_todo(todo_item["id"], called_from_notification=True)
            item_changed = True
        elif result == QDialog.DialogCode.Accepted + 1:
            snooze_duration = dialog.get_snooze_duration()
            if snooze_duration:
                snooze_until_dt = datetime.now(timezone.utc) + snooze_duration
                current_ref.update(
                    {
                        "snoozeUntil": snooze_until_dt.isoformat(),
                        "notifiedForReminder": False,
                        "notifiedForDue": False,
                    }
                )
                item_changed = True

        if item_changed:
            save_todos(self.todos)
            self.update_list_widget()

    # --- 任务操作 ---
    def show_add_task_dialog(self) -> None:
        dialog = TaskEditDialog(parent=self)
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
                    self.todos[index].update(
                        {
                            "text": updated_data["text"],
                            "priority": updated_data["priority"],
                            "dueDate": updated_data["dueDate"],
                            "reminderOffset": updated_data["reminderOffset"],
                            "snoozeUntil": None,
                            "notifiedForReminder": False,
                            "notifiedForDue": False,
                            "lastNotifiedAt": None,
                        }
                    )
                    if normalized_id in self.active_notifications:
                        self.active_notifications.pop(normalized_id).close()
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
            if normalized_id in self.active_notifications:
                self.active_notifications.pop(normalized_id).close()
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
                    if normalized_id in self.active_notifications:
                        self.active_notifications.pop(normalized_id).close()
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

        current_time_utc = datetime.now(timezone.utc)
        for todo_data in processed:
            list_item = QListWidgetItem(self.list_widget)
            item_widget = TodoItemWidget(todo_data.copy())
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
        empty_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-style: italic; font-size: 12pt; background-color: transparent;"
        )
        empty_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        container_layout.addWidget(empty_label, alignment=Qt.AlignmentFlag.AlignCenter)
        container_layout.addStretch()

        viewport_size = self.list_widget.viewport().size() if self.list_widget.viewport() else self.list_widget.size()
        empty_item.setSizeHint(QSize(max(viewport_size.width() - 10, 200), max(viewport_size.height(), 160)))
        self.list_widget.addItem(empty_item)
        self.list_widget.setItemWidget(empty_item, empty_container)

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
        self.show_add_task_dialog()

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

    # --- 状态保存 ---
    def save_geometry_and_state(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.sync()

    def restore_geometry_and_state(self) -> None:
        geom_bytes = self.settings.value("geometry")
        state_bytes = self.settings.value("windowState")
        default_size = QSize(420, 600)
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
            dw = min(max(self.minimumSizeHint().width(), 420), int(screen_geom.width() * 0.85))
            dh = min(max(self.minimumSizeHint().height(), 600), int(screen_geom.height() * 0.85))
            self.resize(QSize(dw, dh))
            self._center_window()
            if self.isMinimized() or not self.isVisible():
                self.showNormal()

    # --- 关闭流程 ---
    def closeEvent(self, event: QEvent) -> None:  # noqa: N802
        for dialog_id in list(self.active_notifications.keys()):
            dialog = self.active_notifications.pop(dialog_id)
            dialog.reject()
            dialog.deleteLater()

        self.save_geometry_and_state()

        if self.tray_icon and self.tray_icon.isVisible() and not self._quitting_app:
            self.hide()
            event.ignore()
            self.tray_icon.showMessage(
                APP_NAME,
                "应用已最小化到系统托盘。",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
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
