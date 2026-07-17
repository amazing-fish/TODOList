"""应用所用对话框。"""
from __future__ import annotations

from datetime import datetime, timedelta, time, timezone
from typing import Optional

from PySide6.QtCore import QDateTime, QTime, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpacerItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QMenu,
    QTimeEdit,
)

from .constants import (
    APP_ICON_PATH,
    REMINDER_OPTIONS_MAP,
    REMINDER_SECONDS_TO_TEXT_MAP,
)
from .utils import get_icon
from .theme import ThemeColors, get_theme_manager


def _default_due_datetime(now_qdt: QDateTime) -> QDateTime:
    target = now_qdt.addSecs(3600)
    hidden_msecs = target.time().second() * 1000 + target.time().msec()
    return target.addMSecs(-hidden_msecs)


def _local_now() -> datetime:
    return datetime.now().astimezone()


class NotificationDialog(QDialog):
    """在一个软件窗口中汇总待处理的任务提醒。"""

    complete_requested = Signal(list)
    snooze_requested = Signal(object, object)

    def __init__(self, requests: list[tuple[dict, bool]], parent=None):
        super().__init__(parent)
        self._task_rows: dict[int, dict[str, object]] = {}
        self._theme_manager = get_theme_manager()
        self._palette: ThemeColors = self._theme_manager.current_palette
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self._build_ui(parent)
        self.add_or_update_tasks(requests)
        self._apply_palette(self._palette)

    def _build_ui(self, parent=None) -> None:
        self.setWindowTitle("任务提醒")
        self.setWindowIcon(get_icon(APP_ICON_PATH, "🔔"))
        self.setMinimumWidth(560)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        self.title_label = QLabel()
        layout.addWidget(self.title_label)

        self.tasks_container = QWidget()
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setContentsMargins(0, 0, 0, 0)
        self.tasks_layout.setSpacing(8)
        self.tasks_scroll = QScrollArea()
        self.tasks_scroll.setWidgetResizable(True)
        self.tasks_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.tasks_scroll.setMaximumHeight(320)
        self.tasks_scroll.setWidget(self.tasks_container)
        layout.addWidget(self.tasks_scroll)

        button_layout = QHBoxLayout()
        self.complete_button = QPushButton(get_icon("", "✓"), "完成选中")
        self.complete_button.clicked.connect(self._emit_complete_requested)
        self.dismiss_button = QPushButton("忽略全部")
        self.dismiss_button.clicked.connect(self.reject)

        button_layout.addWidget(self.complete_button)
        button_layout.addSpacerItem(
            QSpacerItem(20, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        button_layout.addWidget(self.dismiss_button)
        layout.addLayout(button_layout)

    def add_or_update_tasks(self, requests: list[tuple[dict, bool]]) -> None:
        for todo_item, is_due in requests:
            todo_id = int(todo_item["id"])
            existing = self._task_rows.get(todo_id)
            if existing:
                existing["todo_item"] = todo_item
                existing["is_due"] = bool(existing["is_due"] or is_due)
                self._update_task_row(todo_id)
                continue

            row_widget = QWidget()
            row_widget.setObjectName("notificationRow")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(10, 8, 10, 8)
            row_layout.setSpacing(10)

            checkbox = QCheckBox()
            checkbox.setObjectName(f"notificationSelect_{todo_id}")
            checkbox.setChecked(True)
            checkbox.setToolTip("选择此任务进行批量完成")
            row_layout.addWidget(checkbox)

            content_layout = QVBoxLayout()
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(3)
            text_label = QLabel()
            text_label.setWordWrap(True)
            text_font = text_label.font()
            text_font.setBold(True)
            text_label.setFont(text_font)
            detail_label = QLabel()
            status_label = QLabel()
            status_label.setObjectName(f"notificationStatus_{todo_id}")
            content_layout.addWidget(text_label)
            content_layout.addWidget(detail_label)
            content_layout.addWidget(status_label)
            row_layout.addLayout(content_layout, 1)

            snooze_widget = QWidget(row_widget)
            snooze_layout = QHBoxLayout(snooze_widget)
            snooze_layout.setContentsMargins(0, 0, 0, 0)
            snooze_layout.setSpacing(1)

            snooze_default_button = QPushButton(
                get_icon("", "⏰"), " 推迟 15 分钟", snooze_widget
            )
            snooze_default_button.setObjectName(
                f"notificationSnoozeDefault_{todo_id}"
            )
            snooze_default_button.setProperty("snoozeRole", "default")
            snooze_default_button.setToolTip("将此任务推迟 15 分钟")
            snooze_default_button.clicked.connect(
                lambda _checked=False, task_id=todo_id: self.snooze_default(task_id)
            )

            snooze_menu_button = QPushButton("▼", snooze_widget)
            snooze_menu_button.setObjectName(f"notificationSnoozeMenu_{todo_id}")
            snooze_menu_button.setProperty("snoozeRole", "menu")
            snooze_menu_button.setToolTip("选择此任务的推迟时间")
            snooze_menu_button.setFixedWidth(30)

            snooze_menu = QMenu(snooze_menu_button)
            snooze_actions = (
                ("15分钟后", self.snooze_default),
                ("1小时后", self.snooze_1_hour),
                ("晚上8点", self.snooze_8pm),
                ("明天上午9点", self.snooze_tomorrow_9am),
            )
            for label, callback in snooze_actions:
                action = snooze_menu.addAction(label)
                action.triggered.connect(
                    lambda _checked=False, task_id=todo_id, handler=callback: handler(
                        task_id
                    )
                )
            snooze_menu_button.setMenu(snooze_menu)

            snooze_layout.addWidget(snooze_default_button)
            snooze_layout.addWidget(snooze_menu_button)
            row_layout.addWidget(snooze_widget)

            self.tasks_layout.addWidget(row_widget)
            self._task_rows[todo_id] = {
                "todo_item": todo_item,
                "is_due": is_due,
                "widget": row_widget,
                "checkbox": checkbox,
                "text_label": text_label,
                "detail_label": detail_label,
                "status_label": status_label,
                "snooze_default_button": snooze_default_button,
                "snooze_menu_button": snooze_menu_button,
                "snooze_menu": snooze_menu,
            }
            self._update_task_row(todo_id)

        self._update_title()
        self._apply_palette(self._palette)
        self._adjust_size_and_position()

    def _update_task_row(self, todo_id: int) -> None:
        row = self._task_rows[todo_id]
        todo_item = row["todo_item"]
        row["text_label"].setText(str(todo_item.get("text", "无内容")))
        row["detail_label"].setText(self._format_due_text(todo_item))
        row["status_label"].setText("已到期" if row["is_due"] else "提前提醒")

    def _format_due_text(self, todo_item: dict) -> str:
        due_date_str = todo_item.get("dueDate")
        if not due_date_str:
            return "未设置截止时间"
        try:
            due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        except ValueError:
            return "截止时间格式错误"
        return f"截止时间: {due_date.astimezone().strftime('%Y-%m-%d %H:%M')}"

    def _update_title(self) -> None:
        self.title_label.setText(f"{len(self._task_rows)} 个任务需要处理")

    def _adjust_size_and_position(self) -> None:
        visible_rows_height = min(320, max(80, len(self._task_rows) * 72))
        self.tasks_scroll.setFixedHeight(visible_rows_height)
        self.adjustSize()
        parent = self.parentWidget()
        screen = parent.screen() if parent and hasattr(parent, "screen") else None
        if screen:
            screen_geo = screen.availableGeometry()
            x = screen_geo.right() - self.width() - 20
            y = screen_geo.bottom() - self.height() - 20
            self.move(max(screen_geo.left(), x), max(screen_geo.top(), y))

    def task_ids(self) -> list[int]:
        return list(self._task_rows)

    def selected_task_ids(self) -> list[int]:
        return [
            todo_id
            for todo_id, row in self._task_rows.items()
            if row["checkbox"].isChecked()
        ]

    def remove_tasks(self, task_ids: list[int]) -> None:
        for todo_id in task_ids:
            row = self._task_rows.pop(int(todo_id), None)
            if not row:
                continue
            self.tasks_layout.removeWidget(row["widget"])
            row["widget"].deleteLater()
        self._update_title()
        self._adjust_size_and_position()
        if not self._task_rows:
            self.close()

    def _emit_complete_requested(self) -> None:
        selected_ids = self.selected_task_ids()
        if selected_ids:
            self.complete_requested.emit(selected_ids)

    def _apply_palette(self, palette: ThemeColors) -> None:
        self._palette = palette
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {palette.background};
                border: 1px solid {palette.card_border};
                border-radius: 8px;
            }}
            QLabel {{ color: {palette.text_primary}; font-size: 11pt; }}
            QWidget#notificationRow {{
                background-color: {palette.secondary_background};
                border: 1px solid {palette.card_border};
                border-radius: 6px;
            }}
            QScrollArea {{ background-color: transparent; border: none; }}
            QCheckBox {{ color: {palette.text_primary}; spacing: 8px; }}
            QPushButton {{
                background-color: {palette.accent}; color: {palette.inverse_text}; border: none;
                padding: 8px 12px; border-radius: 4px; font-size: 10pt;
            }}
            QPushButton:hover {{ background-color: {palette.accent_hover}; }}
            QPushButton[snoozeRole="default"], QPushButton[snoozeRole="menu"] {{
                background-color: {palette.priority_medium};
                color: {palette.inverse_text};
                padding-top: 8px;
                padding-bottom: 8px;
            }}
            QPushButton[snoozeRole="default"]:hover, QPushButton[snoozeRole="menu"]:hover {{
                background-color: {palette.due_warning};
            }}
            QPushButton[snoozeRole="default"] {{
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding-left: 12px;
                padding-right: 12px;
            }}
            QPushButton[snoozeRole="menu"] {{
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                padding-left: 6px;
                padding-right: 6px;
            }}
            QPushButton[snoozeRole="menu"]::menu-indicator {{ image: none; }}
            QMenu {{
                background-color: {palette.background};
                color: {palette.text_primary};
                border: 1px solid {palette.card_border};
                padding: 4px;
            }}
            QMenu::item {{ padding: 7px 20px; border-radius: 3px; }}
            QMenu::item:selected {{
                background-color: {palette.accent};
                color: {palette.inverse_text};
            }}
            """
        )
        self.title_label.setStyleSheet(
            f"font-size: 14pt; color: {palette.due_warning}; font-weight: bold;"
        )
        for row in self._task_rows.values():
            row["detail_label"].setStyleSheet(
                f"font-size: 9pt; color: {palette.text_secondary};"
            )
            status_color = palette.due_critical if row["is_due"] else palette.due_warning
            row["status_label"].setStyleSheet(
                f"font-size: 9pt; color: {status_color}; font-weight: bold;"
            )

    @Slot(ThemeColors)
    def _on_theme_changed(self, palette: ThemeColors) -> None:
        self._apply_palette(palette)

    def _emit_snooze_requested(self, todo_id: int, duration: timedelta) -> None:
        if todo_id in self._task_rows:
            self.snooze_requested.emit(todo_id, duration)

    def snooze_default(self, todo_id: int) -> None:
        self._emit_snooze_requested(todo_id, timedelta(minutes=15))

    def snooze_1_hour(self, todo_id: int) -> None:
        self._emit_snooze_requested(todo_id, timedelta(hours=1))

    def snooze_tomorrow_9am(self, todo_id: int) -> None:
        now = _local_now()
        tomorrow_date = now.date() + timedelta(days=1)
        target_dt = datetime.combine(tomorrow_date, time(9, 0), tzinfo=now.tzinfo)
        self._emit_snooze_requested(todo_id, target_dt - now)

    def snooze_8pm(self, todo_id: int) -> None:
        now = _local_now()
        target_dt = datetime.combine(now.date(), time(20, 0), tzinfo=now.tzinfo)
        if target_dt <= now:
            target_dt = datetime.combine(
                now.date() + timedelta(days=1),
                time(20, 0),
                tzinfo=now.tzinfo,
            )
        self._emit_snooze_requested(todo_id, target_dt - now)


class TaskEditDialog(QDialog):
    """添加或编辑任务的对话框。"""

    def __init__(self, todo_item: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.todo_item = todo_item
        self.date_edit: Optional[QDateEdit] = None
        self.time_edit: Optional[QTimeEdit] = None
        self._preserved_due_selection: Optional[tuple[str, str]] = None
        self._preserved_due_date_iso: Optional[str] = None
        self._theme_manager = get_theme_manager()
        self._palette: ThemeColors = self._theme_manager.current_palette
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self._build_ui()
        if self.todo_item:
            self.setWindowTitle("编辑待办事项")
            self.populate_fields()
        else:
            self.setWindowTitle("添加新的待办事项")

    def _build_ui(self) -> None:
        from PySide6.QtCore import QDate
        from PySide6.QtWidgets import QComboBox, QFrame, QTextEdit

        self.setMinimumWidth(500)
        self.setWindowIcon(get_icon(APP_ICON_PATH, "T"))
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        self.info_label = QLabel()
        self.info_label.setObjectName("editInfoLabel")
        self.info_label.setWordWrap(True)
        self.info_label.setVisible(False)
        layout.addWidget(self.info_label)

        layout.addWidget(QLabel("任务内容:"))
        self.task_input = QTextEdit()
        self.task_input.setPlaceholderText("输入待办事项内容 (可多行)...")
        self.task_input.setMinimumHeight(60)
        layout.addWidget(self.task_input)

        options_layout = QHBoxLayout()
        options_layout.setSpacing(10)

        priority_layout = QVBoxLayout()
        priority_layout.addWidget(QLabel("重要性:"))
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["高", "中", "低"])
        self.priority_combo.setCurrentText("中")
        priority_layout.addWidget(self.priority_combo)
        priority_layout.addStretch()
        options_layout.addLayout(priority_layout)

        reminder_layout = QVBoxLayout()
        reminder_layout.addWidget(QLabel("提前提醒:"))
        self.reminder_combo = QComboBox()
        self.reminder_combo.addItems(list(REMINDER_OPTIONS_MAP.keys()))
        self.reminder_combo.setCurrentText("到期时")
        reminder_layout.addWidget(self.reminder_combo)
        reminder_layout.addStretch()
        options_layout.addLayout(reminder_layout)

        layout.addLayout(options_layout)

        due_date_frame = QFrame()
        due_date_layout = QVBoxLayout(due_date_frame)
        due_date_layout.setContentsMargins(0, 0, 0, 0)

        self.set_due_date_button = QPushButton("设置截止时间")
        self.set_due_date_button.setObjectName("setDueDateButton")
        self.set_due_date_button.setCheckable(True)
        self.set_due_date_button.toggled.connect(self.toggle_due_date_controls)
        due_date_layout.addWidget(self.set_due_date_button)

        self.due_date_controls_widget = QWidget()
        due_date_controls_layout = QHBoxLayout(self.due_date_controls_widget)
        due_date_controls_layout.setContentsMargins(0, 5, 0, 0)
        due_date_controls_layout.addWidget(QLabel("时间:"))
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        due_date_controls_layout.addWidget(self.time_edit, 1)
        due_date_controls_layout.addSpacerItem(QSpacerItem(10, 0))
        due_date_controls_layout.addWidget(QLabel("日期:"))
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumDate(QDate(2000, 1, 1))
        self.date_edit.setDate(QDate.currentDate())
        due_date_controls_layout.addWidget(self.date_edit, 1)
        due_date_layout.addWidget(self.due_date_controls_widget)

        layout.addWidget(due_date_frame)
        self.toggle_due_date_controls(False)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        if not self.todo_item:
            default_due = _default_due_datetime(QDateTime.currentDateTime())
            self.date_edit.setDate(default_due.date())
            self.time_edit.setTime(default_due.time())
            self._preserved_due_selection = self._current_due_selection()
            py_default_due_utc = default_due.toUTC().toPython()
            if py_default_due_utc.tzinfo is None:
                py_default_due_utc = py_default_due_utc.replace(tzinfo=timezone.utc)
            self._preserved_due_date_iso = py_default_due_utc.isoformat()

        self.resize(400, 300)
        self._apply_palette(self._palette)

    def _apply_palette(self, palette: ThemeColors) -> None:
        self._palette = palette
        self.setStyleSheet(
            f"""
            QDialog {{ background-color: {palette.background}; }}
            QLabel {{ font-size: 10pt; color: {palette.text_primary}; }}
            QLabel#editInfoLabel {{
                font-size: 9pt;
                color: {palette.due_warning};
                background-color: {palette.secondary_background};
                border-left: 3px solid {palette.due_warning};
                border-radius: 4px;
                padding: 6px 10px;
            }}
            QTextEdit, QComboBox, QDateEdit, QTimeEdit {{
                padding: 9px; border: 1px solid {palette.input_border}; border-radius: 4px;
                font-size: 10pt; background-color: {palette.input_background};
                color: {palette.text_primary};
            }}
            QTextEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus {{
                border: 1.5px solid {palette.accent};
            }}
            QCalendarWidget QWidget {{
                background-color: {palette.secondary_background};
                color: {palette.text_primary};
            }}
            QPushButton#setDueDateButton {{
                background-color: {palette.accent};
                color: {palette.inverse_text};
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
            }}
            QPushButton#setDueDateButton:checked {{
                background-color: {palette.accent_hover};
            }}
            QDialogButtonBox QPushButton {{
                background-color: {palette.accent};
                color: {palette.inverse_text};
                border-radius: 4px;
                padding: 6px 14px;
            }}
            QDialogButtonBox QPushButton:hover {{ background-color: {palette.accent_hover}; }}
            """
        )

    @Slot(ThemeColors)
    def _on_theme_changed(self, palette: ThemeColors) -> None:
        self._apply_palette(palette)

    def populate_fields(self) -> None:
        if not self.todo_item:
            return

        from PySide6.QtCore import QDateTime, QTimeZone

        self.task_input.setPlainText(self.todo_item["text"])
        self.priority_combo.setCurrentText(self.todo_item.get("priority", "中"))

        if self.todo_item.get("completed", False):
            self.info_label.setText("提示：该任务已完成，修改内容会立即同步，请确认后保存。")
            self.info_label.setVisible(True)
        else:
            self.info_label.setVisible(False)

        if self.todo_item.get("dueDate"):
            try:
                parsed_due_date = datetime.fromisoformat(
                    self.todo_item["dueDate"].replace("Z", "+00:00")
                )
                if parsed_due_date.tzinfo is None:
                    due_dt_utc = parsed_due_date.replace(tzinfo=timezone.utc)
                else:
                    due_dt_utc = parsed_due_date.astimezone(timezone.utc)
                qdt_utc = QDateTime.fromMSecsSinceEpoch(
                    int(due_dt_utc.timestamp() * 1000),
                    QTimeZone.utc(),
                )
                local_qdt = qdt_utc.toLocalTime()

                self.date_edit.setDate(local_qdt.date())
                self.time_edit.setTime(local_qdt.time())
                self._preserved_due_selection = self._current_due_selection()
                self._preserved_due_date_iso = self.todo_item["dueDate"]
                self.set_due_date_button.setChecked(True)
            except ValueError:
                print(f"错误: 编辑任务时截止日期格式无效: {self.todo_item['dueDate']}")
                self.set_due_date_button.setChecked(False)
        else:
            self.set_due_date_button.setChecked(False)

        self.reminder_combo.setCurrentText(
            REMINDER_SECONDS_TO_TEXT_MAP.get(self.todo_item.get("reminderOffset", 0), "到期时")
        )

    def toggle_due_date_controls(self, checked: bool) -> None:
        self.due_date_controls_widget.setVisible(checked)
        self.set_due_date_button.setText("清除截止时间" if checked else "设置截止时间")

    def _current_due_selection(self) -> tuple[str, str]:
        return (
            self.date_edit.date().toString("yyyy-MM-dd"),
            self.time_edit.time().toString("HH:mm"),
        )

    def _serialize_due_date(self) -> Optional[str]:
        from PySide6.QtCore import QDateTime, QTime

        if not self.set_due_date_button.isChecked():
            return None

        if (
            self._preserved_due_date_iso
            and self._current_due_selection() == self._preserved_due_selection
        ):
            return self._preserved_due_date_iso

        selected_time = self.time_edit.time()
        visible_time = QTime(selected_time.hour(), selected_time.minute())
        py_due_date_utc = QDateTime(self.date_edit.date(), visible_time).toUTC().toPython()
        if py_due_date_utc.tzinfo is None:
            py_due_date_utc = py_due_date_utc.replace(tzinfo=timezone.utc)
        return py_due_date_utc.isoformat()

    def get_task_data(self) -> dict:
        return {
            "text": self.task_input.toPlainText().strip(),
            "priority": self.priority_combo.currentText(),
            "dueDate": self._serialize_due_date(),
            "reminderOffset": REMINDER_OPTIONS_MAP.get(self.reminder_combo.currentText(), 0),
        }

    def accept(self) -> None:  # type: ignore[override]
        text = self.task_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "输入错误", "待办事项内容不能为空！")
            return

        due_date_iso = self._serialize_due_date()
        if due_date_iso:
            py_due_date_utc = datetime.fromisoformat(due_date_iso.replace("Z", "+00:00"))
            if py_due_date_utc.tzinfo is None:
                py_due_date_utc = py_due_date_utc.replace(tzinfo=timezone.utc)
            else:
                py_due_date_utc = py_due_date_utc.astimezone(timezone.utc)
            if self.todo_item is None and py_due_date_utc <= datetime.now(timezone.utc):
                QMessageBox.warning(self, "时间错误", "新任务的截止时间必须是未来的某个时间点！")
                return

        super().accept()


__all__ = ["NotificationDialog", "TaskEditDialog"]
