"""应用所用对话框。"""
from __future__ import annotations

from datetime import datetime, timedelta, time, timezone
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QMenu,
)

from .constants import (
    APP_ICON_PATH,
    CALENDAR_ICON_PATH,
    REMINDER_OPTIONS_MAP,
    REMINDER_SECONDS_TO_TEXT_MAP,
)
from .utils import get_icon
from .theme import ThemeColors, get_theme_manager


class NotificationDialog(QDialog):
    """提醒任务的弹窗对话框。"""

    def __init__(self, todo_item: dict, parent=None):
        super().__init__(parent)
        self.todo_item = todo_item
        self.snooze_duration: Optional[timedelta] = None
        self._theme_manager = get_theme_manager()
        self._palette: ThemeColors = self._theme_manager.current_palette
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self._build_ui(parent)
        self._apply_palette(self._palette)

    def _build_ui(self, parent=None) -> None:
        self.setWindowTitle("任务提醒")
        self.setWindowIcon(get_icon(APP_ICON_PATH, "🔔"))
        self.setMinimumWidth(350)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        self.title_label = QLabel("<b>任务到期提醒</b>")
        layout.addWidget(self.title_label)

        self.text_label = QLabel(f"任务: <b>{self.todo_item['text']}</b>")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

        if self.todo_item.get("dueDate"):
            try:
                due_date = datetime.fromisoformat(self.todo_item["dueDate"].replace("Z", "+00:00"))
                self.due_label = QLabel(
                    f"截止时间: {due_date.astimezone().strftime('%Y-%m-%d %H:%M')}"
                )
                layout.addWidget(self.due_label)
            except ValueError:
                print(
                    f"提醒对话框中任务 '{self.todo_item['text']}' 的截止日期格式无效: {self.todo_item['dueDate']}"
                )
                self.due_label = None
        else:
            self.due_label = None

        button_layout = QHBoxLayout()
        self.complete_button = QPushButton(get_icon("", "✓"), "标记为完成")
        self.complete_button.clicked.connect(self.accept)
        self.dismiss_button = QPushButton("忽略")
        self.dismiss_button.clicked.connect(self.reject)

        snooze_widget = QWidget()
        snooze_layout = QHBoxLayout(snooze_widget)
        snooze_layout.setContentsMargins(0, 0, 0, 0)
        snooze_layout.setSpacing(1)

        self.snooze_default_button = QPushButton(get_icon("", "⏰"), " 15分钟后提醒")
        self.snooze_default_button.setObjectName("snoozeDefaultButton")
        self.snooze_default_button.clicked.connect(self.snooze_default)

        self.snooze_menu_button = QPushButton("▼")
        self.snooze_menu_button.setObjectName("snoozeMenuButton")
        self.snooze_menu_button.setFixedWidth(30)

        snooze_menu = QMenu(self)
        snooze_menu.addAction("15分钟后", self.snooze_default)
        snooze_menu.addAction("1小时后", self.snooze_1_hour)
        snooze_menu.addAction("晚上8点", self.snooze_8pm)
        snooze_menu.addAction("明天上午9点", self.snooze_tomorrow_9am)
        self.snooze_menu_button.setMenu(snooze_menu)

        snooze_layout.addWidget(self.snooze_default_button)
        snooze_layout.addWidget(self.snooze_menu_button)

        button_layout.addWidget(self.complete_button)
        button_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        button_layout.addWidget(snooze_widget)
        button_layout.addWidget(self.dismiss_button)
        layout.addLayout(button_layout)

        if parent:
            screen = parent.screen() if hasattr(parent, "screen") else None
            if screen:
                screen_geo = screen.availableGeometry()
                self.adjustSize()
                x = screen_geo.right() - self.width() - 20
                y = screen_geo.bottom() - self.height() - 20
                self.move(max(screen_geo.left(), x), max(screen_geo.top(), y))

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
            QPushButton {{
                background-color: {palette.accent}; color: {palette.inverse_text}; border: none;
                padding: 8px 12px; border-radius: 4px; font-size: 10pt;
            }}
            QPushButton:hover {{ background-color: {palette.accent_hover}; }}
            QPushButton#snoozeDefaultButton, QPushButton#snoozeMenuButton {{
                background-color: {palette.priority_medium};
                color: {palette.inverse_text};
                padding-top: 8px;
                padding-bottom: 8px;
            }}
            QPushButton#snoozeDefaultButton:hover, QPushButton#snoozeMenuButton:hover {{
                background-color: {palette.due_warning};
            }}
            QPushButton#snoozeDefaultButton {{
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding-left: 12px;
                padding-right: 12px;
            }}
            QPushButton#snoozeMenuButton {{
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                padding-left: 6px;
                padding-right: 6px;
            }}
            QPushButton#snoozeMenuButton::menu-indicator {{ image: none; }}
            """
        )
        self.title_label.setStyleSheet(
            f"font-size: 14pt; color: {palette.due_warning}; font-weight: bold;"
        )
        if self.due_label is not None:
            self.due_label.setStyleSheet(
                f"font-size: 10pt; color: {palette.text_secondary};"
            )

    @Slot(ThemeColors)
    def _on_theme_changed(self, palette: ThemeColors) -> None:
        self._apply_palette(palette)

    def _set_snooze_and_close(self, duration: timedelta) -> None:
        self.snooze_duration = duration
        self.done(QDialog.DialogCode.Accepted + 1)

    def snooze_default(self) -> None:
        self._set_snooze_and_close(timedelta(minutes=15))

    def snooze_1_hour(self) -> None:
        self._set_snooze_and_close(timedelta(hours=1))

    def snooze_tomorrow_9am(self) -> None:
        now = datetime.now().astimezone()
        tomorrow_date = now.date() + timedelta(days=1)
        target_dt = datetime.combine(tomorrow_date, time(9, 0), tzinfo=now.tzinfo)
        self._set_snooze_and_close(target_dt - now)

    def snooze_8pm(self) -> None:
        now = datetime.now().astimezone()
        target_dt = datetime.combine(now.date(), time(20, 0), tzinfo=now.tzinfo)
        if target_dt <= now:
            target_dt = datetime.combine(
                now.date() + timedelta(days=1),
                time(20, 0),
                tzinfo=now.tzinfo,
            )
        self._set_snooze_and_close(target_dt - now)

    def get_snooze_duration(self) -> Optional[timedelta]:
        return self.snooze_duration


class TaskEditDialog(QDialog):
    """添加或编辑任务的对话框。"""

    def __init__(self, todo_item: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.todo_item = todo_item
        self._internal_due_date = None
        self.time_edit: Optional[QDateTimeEdit] = None
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
        from PySide6.QtCore import QDate, QDateTime, QTime
        from PySide6.QtWidgets import QComboBox, QFrame, QTextEdit

        self.setMinimumWidth(500)
        self.setWindowIcon(get_icon(APP_ICON_PATH, "T"))
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

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
        due_date_controls_layout.addWidget(QLabel("日期:"))
        self.selected_date_label = QLabel("未设置")
        self.selected_date_label.setObjectName("selectedDateLabel")
        due_date_controls_layout.addWidget(self.selected_date_label)
        self.pick_date_button = QPushButton(icon=get_icon(CALENDAR_ICON_PATH, "📅"))
        self.pick_date_button.setObjectName("pickDateButton")
        self.pick_date_button.setToolTip("选择日期")
        self.pick_date_button.clicked.connect(self.show_calendar_popup)
        due_date_controls_layout.addWidget(self.pick_date_button)
        due_date_controls_layout.addSpacerItem(QSpacerItem(10, 0))
        due_date_controls_layout.addWidget(QLabel("时间:"))
        self.time_edit = QDateTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setCalendarPopup(False)
        due_date_controls_layout.addWidget(self.time_edit, 1)
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
            now_qdt = QDateTime.currentDateTime()
            default_qtime = now_qdt.addSecs(3600).time()
            if default_qtime.hour() < 7:
                default_qtime = QTime(9, 0, 0)
            self.time_edit.setDateTime(QDateTime(QDate.currentDate(), default_qtime))

        self.resize(400, 300)
        self._apply_palette(self._palette)

    def _apply_palette(self, palette: ThemeColors) -> None:
        self._palette = palette
        self.setStyleSheet(
            f"""
            QDialog {{ background-color: {palette.background}; }}
            QLabel {{ font-size: 10pt; color: {palette.text_primary}; }}
            QTextEdit, QComboBox, QDateTimeEdit {{
                padding: 9px; border: 1px solid {palette.input_border}; border-radius: 4px;
                font-size: 10pt; background-color: {palette.input_background};
                color: {palette.text_primary};
            }}
            QTextEdit:focus, QComboBox:focus, QDateTimeEdit:focus {{
                border: 1.5px solid {palette.accent};
            }}
            QPushButton#pickDateButton {{
                padding: 7px; border: 1px solid {palette.input_border}; border-radius: 4px;
                background-color: {palette.secondary_background};
                color: {palette.text_primary};
            }}
            QPushButton#pickDateButton:hover {{ background-color: {palette.action_hover_bg}; }}
            QLabel#selectedDateLabel {{
                 padding: 9px; border: 1px solid {palette.input_border}; border-radius: 4px;
                 background-color: {palette.secondary_background};
                 color: {palette.text_secondary};
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

        from PySide6.QtCore import QDateTime, Qt, QDate

        self.task_input.setPlainText(self.todo_item["text"])
        self.priority_combo.setCurrentText(self.todo_item.get("priority", "中"))

        if self.todo_item.get("dueDate"):
            try:
                due_dt_utc = datetime.fromisoformat(self.todo_item["dueDate"].replace("Z", "+00:00"))
                qdt_utc = QDateTime(
                    due_dt_utc.year,
                    due_dt_utc.month,
                    due_dt_utc.day,
                    due_dt_utc.hour,
                    due_dt_utc.minute,
                    due_dt_utc.second,
                    due_dt_utc.microsecond // 1000,
                    Qt.TimeSpec.UTC,
                )
                local_qdt = qdt_utc.toLocalTime()

                self._internal_due_date = local_qdt.date()
                self.time_edit.setDateTime(local_qdt)
                self.set_due_date_button.setChecked(True)
                self.update_selected_date_label()
            except ValueError:
                print(f"错误: 编辑任务时截止日期格式无效: {self.todo_item['dueDate']}")
                self.set_due_date_button.setChecked(False)
        else:
            self.set_due_date_button.setChecked(False)

        self.reminder_combo.setCurrentText(
            REMINDER_SECONDS_TO_TEXT_MAP.get(self.todo_item.get("reminderOffset", 0), "到期时")
        )

    def toggle_due_date_controls(self, checked: bool) -> None:
        from PySide6.QtCore import QDate

        self.due_date_controls_widget.setVisible(checked)
        self.set_due_date_button.setText("清除截止时间" if checked else "设置截止时间")
        if checked:
            if not self._internal_due_date:
                self._internal_due_date = QDate.currentDate()
            self.update_selected_date_label()
        else:
            self._internal_due_date = None

    def update_selected_date_label(self) -> None:
        from PySide6.QtCore import QDate

        if self._internal_due_date:
            if self._internal_due_date == QDate.currentDate():
                text = "<b>今日</b>"
            elif self._internal_due_date == QDate.currentDate().addDays(1):
                text = "<b>明日</b>"
            else:
                text = self._internal_due_date.toString("yyyy-MM-dd")
            self.selected_date_label.setText(text)
        else:
            self.selected_date_label.setText("未设置")

    def show_calendar_popup(self) -> None:
        from PySide6.QtCore import QDate

        calendar_dialog = QDialog(self)
        calendar_dialog.setWindowTitle("选择截止日期")
        calendar_dialog.setWindowIcon(get_icon(CALENDAR_ICON_PATH, "📅"))
        layout = QVBoxLayout(calendar_dialog)
        calendar_widget = QCalendarWidget(calendar_dialog)
        calendar_widget.setGridVisible(True)
        calendar_widget.setSelectedDate(self._internal_due_date or QDate.currentDate())
        calendar_widget.setMinimumDate(QDate(2000, 1, 1))

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(calendar_dialog.accept)
        button_box.rejected.connect(calendar_dialog.reject)
        layout.addWidget(calendar_widget)
        layout.addWidget(button_box)

        calendar_dialog.setStyleSheet(
            f"""
            QDialog {{ background-color: {self._palette.background}; color: {self._palette.text_primary}; }}
            QCalendarWidget QWidget {{
                background-color: {self._palette.secondary_background};
                color: {self._palette.text_primary};
            }}
            QPushButton {{
                background-color: {self._palette.accent};
                color: {self._palette.inverse_text};
                border-radius: 4px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{ background-color: {self._palette.accent_hover}; }}
            """
        )

        if calendar_dialog.exec():
            self._internal_due_date = calendar_widget.selectedDate()
            self.update_selected_date_label()

    def get_task_data(self) -> dict:
        from PySide6.QtCore import QDateTime

        due_date_iso_utc = None
        if self.set_due_date_button.isChecked() and self._internal_due_date:
            py_due_date_utc = QDateTime(self._internal_due_date, self.time_edit.time()).toUTC().toPython()
            if py_due_date_utc.tzinfo is None:
                py_due_date_utc = py_due_date_utc.replace(tzinfo=timezone.utc)
            due_date_iso_utc = py_due_date_utc.isoformat()

        return {
            "text": self.task_input.toPlainText().strip(),
            "priority": self.priority_combo.currentText(),
            "dueDate": due_date_iso_utc,
            "reminderOffset": REMINDER_OPTIONS_MAP.get(self.reminder_combo.currentText(), 0),
        }

    def accept(self) -> None:  # type: ignore[override]
        from PySide6.QtCore import QDateTime

        text = self.task_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "输入错误", "待办事项内容不能为空！")
            return

        if self.set_due_date_button.isChecked() and self._internal_due_date:
            py_due_date_utc = QDateTime(self._internal_due_date, self.time_edit.time()).toUTC().toPython()
            if py_due_date_utc.tzinfo is None:
                py_due_date_utc = py_due_date_utc.replace(tzinfo=timezone.utc)
            if self.todo_item is None and py_due_date_utc <= datetime.now(timezone.utc):
                QMessageBox.warning(self, "时间错误", "新任务的截止时间必须是未来的某个时间点！")
                return

        super().accept()


__all__ = ["NotificationDialog", "TaskEditDialog"]
