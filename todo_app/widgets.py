"""自定义部件。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal, QEvent
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    COLOR_COMPLETED_ITEM_BG,
    COLOR_DUE_CRITICAL,
    COLOR_DUE_WARNING,
    COLOR_PRIMARY_ITEM_BG,
    COLOR_PRIORITY_HIGH,
    COLOR_PRIORITY_LOW,
    COLOR_PRIORITY_MEDIUM,
    COLOR_TEXT_COMPLETED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    DELETE_ICON_PATH,
    DONE_ICON_PATH,
    EDIT_ICON_PATH,
)
from .utils import get_icon, truncate_text_for_width


class TodoItemWidget(QFrame):
    """待办事项卡片。"""

    request_edit = Signal(object)
    request_delete = Signal(object)
    request_toggle_complete = Signal(object)

    def __init__(self, todo_item: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.todo_item = todo_item
        self.original_text = todo_item.get("text", "无内容")
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setObjectName("TodoItemWidget")

        is_completed = self.todo_item.get("completed", False)
        bg_color = COLOR_COMPLETED_ITEM_BG if is_completed else COLOR_PRIMARY_ITEM_BG
        text_color = COLOR_TEXT_COMPLETED if is_completed else COLOR_TEXT_PRIMARY
        text_decoration = "text-decoration: line-through;" if is_completed else ""

        self.setStyleSheet(
            f"""
            QFrame#TodoItemWidget {{
                background-color: {bg_color}; border: 1px solid #CFD8DC;
                border-radius: 6px; padding: 12px; margin-bottom: 8px;
            }}
            QLabel {{ background-color: transparent; }}
            QPushButton {{ background-color: transparent; border: none; padding: 4px; }}
            QPushButton:hover {{ background-color: #B0BEC5; border-radius: 3px; }}
            """
        )

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        self.complete_button = QPushButton()
        self.complete_button.setCheckable(True)
        self.complete_button.setChecked(is_completed)
        self.complete_button.setIcon(get_icon(DONE_ICON_PATH, "✓" if is_completed else "○"))
        self.complete_button.setIconSize(QSize(20, 20))
        self.complete_button.setToolTip("标记为完成/未完成")
        self.complete_button.clicked.connect(self._toggle_complete)
        main_layout.addWidget(self.complete_button)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(4)
        self.task_text_label = QLabel(self.original_text)
        self.task_text_label.setWordWrap(False)
        font = QFont("Segoe UI", 11)
        font.setBold(not is_completed)
        self.task_text_label.setFont(font)
        self.task_text_label.setStyleSheet(f"color: {text_color}; {text_decoration}")

        priority = self.todo_item.get("priority", "中")
        p_color = {"高": COLOR_PRIORITY_HIGH, "中": COLOR_PRIORITY_MEDIUM, "低": COLOR_PRIORITY_LOW}.get(
            priority, COLOR_TEXT_SECONDARY
        )
        self.priority_label = QLabel(
            f"<span style='color:white; background-color:{p_color}; padding:2px 6px; border-radius:3px; font-size:8pt;'>{priority}</span>"
        )
        self.priority_label.setTextFormat(Qt.TextFormat.RichText)
        content_layout.addWidget(self.task_text_label)
        content_layout.addWidget(self.priority_label)
        main_layout.addLayout(content_layout, 1)

        self.timer_display_label = QLabel("无计时")
        self.timer_display_label.setMinimumWidth(80)
        self.timer_display_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.timer_display_label.setStyleSheet(f"font-size: 9pt; color: {COLOR_TEXT_SECONDARY}; {text_decoration}")
        main_layout.addWidget(self.timer_display_label)

        self.actions_container = QWidget()
        actions_layout = QVBoxLayout(self.actions_container)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(5)

        self.edit_button = QPushButton(icon=get_icon(EDIT_ICON_PATH, "✎"))
        self.edit_button.setIconSize(QSize(18, 18))
        self.edit_button.setToolTip("编辑任务")
        self.edit_button.clicked.connect(self._edit_item)
        self.edit_button.setEnabled(not is_completed)

        self.delete_button = QPushButton(icon=get_icon(DELETE_ICON_PATH, "🗑"))
        self.delete_button.setIconSize(QSize(18, 18))
        self.delete_button.setToolTip("删除任务")
        self.delete_button.clicked.connect(self._delete_item)

        actions_layout.addWidget(self.edit_button)
        actions_layout.addWidget(self.delete_button)
        actions_layout.addStretch()

        self.actions_container.setMinimumWidth(35)
        main_layout.addWidget(self.actions_container)
        self.actions_container.setVisible(False)

        self.update_timer_display(datetime.now(timezone.utc))
        self.update_text_display()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self.actions_container.setVisible(True)
        super().enterEvent(event)
        self.update_text_display()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self.actions_container.setVisible(False)
        super().leaveEvent(event)
        self.update_text_display()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.update_text_display()

    def update_text_display(self) -> None:
        total_width = self.width()
        if total_width <= 0:
            return

        margins = 24
        button_width = self.complete_button.width() or 28
        timer_width = self.timer_display_label.minimumWidth()
        actions_width = self.actions_container.width() if self.actions_container.isVisible() else 0
        spacing = 30

        available_width = total_width - margins - button_width - timer_width - actions_width - spacing
        if available_width < 50:
            available_width = 50

        font = self.task_text_label.font()
        truncated_text = truncate_text_for_width(self.original_text, font, available_width, min_chars=6)
        self.task_text_label.setText(truncated_text)

        if truncated_text != self.original_text:
            self.task_text_label.setToolTip(self.original_text)
        else:
            self.task_text_label.setToolTip("")

    def _toggle_complete(self) -> None:
        self.request_toggle_complete.emit(self.todo_item["id"])

    def _edit_item(self) -> None:
        self.request_edit.emit(self.todo_item["id"])

    def _delete_item(self) -> None:
        self.request_delete.emit(self.todo_item["id"])

    def update_timer_display(self, current_time_utc: datetime) -> None:
        is_completed = self.todo_item.get("completed", False)
        self.complete_button.setChecked(is_completed)
        self.complete_button.setIcon(get_icon(DONE_ICON_PATH, "✓" if is_completed else "○"))
        self.edit_button.setEnabled(not is_completed)
        self.edit_button.setToolTip("编辑任务" if not is_completed else "已完成任务不可编辑")

        text_color = COLOR_TEXT_COMPLETED if is_completed else COLOR_TEXT_PRIMARY
        text_decoration = "text-decoration: line-through;" if is_completed else "text-decoration: none;"
        self.task_text_label.setStyleSheet(f"color: {text_color}; {text_decoration}")
        font = self.task_text_label.font()
        font.setBold(not is_completed)
        self.task_text_label.setFont(font)
        self.timer_display_label.setStyleSheet(
            f"font-size: 9pt; color: {COLOR_TEXT_COMPLETED if is_completed else COLOR_TEXT_SECONDARY}; {text_decoration}"
        )

        if is_completed:
            self.timer_display_label.setText("已完成")
            self.timer_display_label.setStyleSheet(
                f"font-size: 9pt; color: {COLOR_TEXT_COMPLETED}; font-style: italic; {text_decoration}"
            )
            self.update_text_display()
            return

        snooze_until_str = self.todo_item.get("snoozeUntil")
        if snooze_until_str:
            try:
                snooze_until_dt = datetime.fromisoformat(snooze_until_str.replace("Z", "+00:00"))
                if snooze_until_dt > current_time_utc:
                    self.timer_display_label.setText(
                        f"推迟: {self._format_timedelta(snooze_until_dt - current_time_utc)}"
                    )
                    self.timer_display_label.setStyleSheet("font-size: 9pt; color: #FF9800;")
                    self.update_text_display()
                    return
            except ValueError:
                print(f"任务 '{self.todo_item.get('text', '')}' 的推迟日期格式错误: {snooze_until_str}")
                self.todo_item["snoozeUntil"] = None

        due_date_str = self.todo_item.get("dueDate")
        if not due_date_str:
            self.timer_display_label.setText("无截止日期")
            self.timer_display_label.setStyleSheet(f"font-size: 9pt; color: {COLOR_TEXT_SECONDARY};")
            self.update_text_display()
            return

        try:
            due_date_dt = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        except ValueError:
            self.timer_display_label.setText("日期格式错误!")
            self.timer_display_label.setStyleSheet("font-size: 9pt; color: red; font-weight: bold;")
            self.update_text_display()
            return

        diff = due_date_dt - current_time_utc
        time_left_str = self._format_timedelta(diff)
        if diff.total_seconds() <= 0:
            self.timer_display_label.setText(f"已到期 ({time_left_str.replace('-', '')})")
            self.timer_display_label.setStyleSheet(
                f"font-size: 10pt; color: {COLOR_DUE_CRITICAL}; font-weight: bold;"
            )
        else:
            self.timer_display_label.setText(f"剩余: {time_left_str}")
            color = COLOR_DUE_WARNING if diff.total_seconds() < 86400 else "#2E7D32"
            self.timer_display_label.setStyleSheet(f"font-size: 9pt; color: {color}; font-weight: bold;")

        self.update_text_display()

    def _format_timedelta(self, diff: timedelta) -> str:
        is_past = diff.total_seconds() < 0
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

        if not parts:
            return "刚刚"

        formatted_str = " ".join(parts[:2])
        return f"-{formatted_str}" if is_past else formatted_str


__all__ = ["TodoItemWidget"]
