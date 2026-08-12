"""应用所用对话框。"""
from __future__ import annotations

from datetime import datetime, timedelta, time, timezone
from typing import Optional

from PySide6.QtCore import QDateTime, QTime, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpacerItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
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


class NotificationDialog(QDialog):
    """在一个软件窗口中汇总待处理的任务提醒。"""

    complete_requested = Signal(list)
    snooze_requested = Signal(list, object)
    ignore_requested = Signal(list)

    def __init__(self, requests: list[tuple[dict, bool]], parent=None):
        super().__init__(parent)
        self._task_rows: dict[int, dict[str, object]] = {}
        self._theme_manager = get_theme_manager()
        self._palette: ThemeColors = self._theme_manager.current_palette
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self._build_ui()
        self.add_or_update_tasks(requests)
        self._apply_palette(self._palette)
        self._relative_time_timer = QTimer(self)
        self._relative_time_timer.setInterval(1000)
        self._relative_time_timer.timeout.connect(self._refresh_relative_times)
        self._relative_time_timer.start()

    def _build_ui(self) -> None:
        self.setWindowTitle("任务提醒")
        self.setWindowIcon(get_icon(APP_ICON_PATH, "🔔"))
        self.setMinimumWidth(460)
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

            action_layout = QHBoxLayout()
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(4)

            complete_action = QPushButton("完成")
            complete_action.setObjectName(f"notificationComplete_{todo_id}")
            complete_action.setProperty("notificationRowAction", True)
            complete_action.setToolTip("仅将此任务标记为完成")
            complete_action.clicked.connect(
                lambda _checked=False, task_id=todo_id: self.complete_requested.emit([task_id])
            )

            snooze_action = QToolButton()
            snooze_action.setText("推迟 1 小时")
            snooze_action.setObjectName(f"notificationSnooze_{todo_id}")
            snooze_action.setProperty("notificationRowAction", True)
            snooze_action.setProperty("notificationSnoozeAction", True)
            snooze_action.setToolTip(
                "点击主按钮将此任务推迟 1 小时；点击箭头选择其他时长"
            )
            snooze_action.setPopupMode(
                QToolButton.ToolButtonPopupMode.MenuButtonPopup
            )
            snooze_action.setMenu(self._build_snooze_menu([todo_id], snooze_action))
            snooze_action.clicked.connect(
                lambda _checked=False, task_id=todo_id: self.snooze_default([task_id])
            )

            ignore_action = QPushButton("忽略")
            ignore_action.setObjectName(f"notificationIgnore_{todo_id}")
            ignore_action.setProperty("notificationRowAction", True)
            ignore_action.setProperty("notificationIgnoreAction", True)
            ignore_action.setToolTip(
                "保留此任务并清除截止时间；不会标记为完成，重新设置截止时间前不再提醒"
            )
            ignore_action.clicked.connect(
                lambda _checked=False, task_id=todo_id: self.ignore_requested.emit([task_id])
            )

            action_layout.addWidget(complete_action)
            action_layout.addWidget(snooze_action)
            action_layout.addWidget(ignore_action)
            row_layout.addLayout(action_layout)

            self.tasks_layout.addWidget(row_widget)
            self._task_rows[todo_id] = {
                "todo_item": todo_item,
                "is_due": is_due,
                "widget": row_widget,
                "text_label": text_label,
                "detail_label": detail_label,
                "status_label": status_label,
                "complete_action": complete_action,
                "snooze_action": snooze_action,
                "ignore_action": ignore_action,
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

    def _refresh_relative_times(self) -> None:
        current_time_utc = datetime.now(timezone.utc)
        for row in self._task_rows.values():
            row["detail_label"].setText(
                self._format_due_text(row["todo_item"], current_time_utc)
            )

    def _format_due_text(
        self, todo_item: dict, current_time_utc: Optional[datetime] = None
    ) -> str:
        due_date_str = todo_item.get("dueDate")
        if not due_date_str:
            return "未设置截止时间"
        try:
            due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        except ValueError:
            return "截止时间格式错误"
        if due_date.tzinfo is None:
            due_date = due_date.astimezone()
        if current_time_utc is None:
            current_time_utc = datetime.now(timezone.utc)
        elif current_time_utc.tzinfo is None:
            current_time_utc = current_time_utc.replace(tzinfo=timezone.utc)
        else:
            current_time_utc = current_time_utc.astimezone(timezone.utc)

        diff = due_date.astimezone(timezone.utc) - current_time_utc
        duration_text = self._format_relative_duration(diff)
        if diff.total_seconds() < 0:
            relative_text = f"已超时 {duration_text}"
        elif diff.total_seconds() > 0:
            relative_text = f"还有 {duration_text}"
        else:
            relative_text = "刚刚到期"
        absolute_text = due_date.astimezone().strftime("%Y-%m-%d %H:%M")
        return f"截止时间: {absolute_text} · {relative_text}"

    @staticmethod
    def _format_relative_duration(diff: timedelta) -> str:
        """沿用主列表计时的单位、取整与最多两段显示语义。"""

        effective_diff = abs(diff)
        days = effective_diff.days
        secs_in_day = effective_diff.seconds
        hours = secs_in_day // 3600
        minutes = (secs_in_day % 3600) // 60
        seconds = secs_in_day % 60
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}时")
        if minutes > 0 and days == 0:
            parts.append(f"{minutes}分")
        if not parts and effective_diff.total_seconds() > 0:
            parts.append(f"{seconds}秒")
        return " ".join(parts[:2]) if parts else "刚刚"

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
            QPushButton, QToolButton {{
                background-color: {palette.accent}; color: {palette.inverse_text}; border: none;
                padding: 8px 12px; border-radius: 4px; font-size: 10pt;
            }}
            QPushButton:hover, QToolButton:hover {{
                background-color: {palette.accent_hover};
            }}
            QPushButton:disabled, QToolButton:disabled {{
                background-color: {palette.card_border}; color: {palette.text_secondary};
            }}
            QPushButton[notificationRowAction="true"],
            QToolButton[notificationRowAction="true"] {{
                padding: 5px 8px; font-size: 9pt;
            }}
            QToolButton[notificationSnoozeAction="true"] {{
                background-color: {palette.priority_medium};
                padding-right: 25px;
            }}
            QToolButton[notificationSnoozeAction="true"]:hover {{
                background-color: {palette.due_warning};
            }}
            QToolButton[notificationSnoozeAction="true"]::menu-button {{
                width: 18px;
                border-left: 1px solid {palette.input_border};
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }}
            QToolButton[notificationSnoozeAction="true"]::menu-button:hover {{
                background-color: {palette.accent_hover};
            }}
            QPushButton[notificationIgnoreAction="true"] {{
                background-color: {palette.due_critical};
            }}
            QMenu {{
                background-color: {palette.background}; color: {palette.text_primary};
                border: 1px solid {palette.card_border}; padding: 4px;
            }}
            QMenu::item {{ padding: 6px 16px; }}
            QMenu::item:selected {{
                background-color: {palette.accent}; color: {palette.inverse_text};
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

    def _build_snooze_menu(
        self,
        todo_ids: list[int],
        parent: Optional[QWidget] = None,
    ) -> QMenu:
        menu = QMenu(parent or self)
        menu.addAction(
            "15分钟后",
            lambda _checked=False: self.snooze_15_minutes(todo_ids),
        )
        menu.addAction(
            "1小时后",
            lambda _checked=False: self.snooze_default(todo_ids),
        )
        menu.addAction(
            "晚上8点",
            lambda _checked=False: self.snooze_8pm(todo_ids),
        )
        menu.addAction(
            "明天上午9点",
            lambda _checked=False: self.snooze_tomorrow_9am(todo_ids),
        )
        return menu

    def _emit_snooze_requested(
        self, duration: timedelta, todo_ids: list[int]
    ) -> None:
        self.snooze_requested.emit(todo_ids, duration)

    def snooze_default(self, todo_ids: list[int]) -> None:
        self._emit_snooze_requested(timedelta(hours=1), todo_ids)

    def snooze_15_minutes(self, todo_ids: list[int]) -> None:
        self._emit_snooze_requested(timedelta(minutes=15), todo_ids)

    def snooze_tomorrow_9am(self, todo_ids: list[int]) -> None:
        now = datetime.now().astimezone()
        tomorrow_date = now.date() + timedelta(days=1)
        target_dt = datetime.combine(tomorrow_date, time(9, 0), tzinfo=now.tzinfo)
        self._emit_snooze_requested(target_dt - now, todo_ids)

    def snooze_8pm(self, todo_ids: list[int]) -> None:
        now = datetime.now().astimezone()
        target_dt = datetime.combine(now.date(), time(20, 0), tzinfo=now.tzinfo)
        if target_dt <= now:
            target_dt = datetime.combine(
                now.date() + timedelta(days=1),
                time(20, 0),
                tzinfo=now.tzinfo,
            )
        self._emit_snooze_requested(target_dt - now, todo_ids)


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
