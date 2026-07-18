"""自定义部件。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal, QEvent, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    DONE_ICON_PATH,
    INCOMPLETE_ICON_PATH,
)
from .utils import get_icon, truncate_text_for_width
from .theme import ThemeColors, get_theme_manager


def _build_action_icon(kind: str, color: str) -> QIcon:
    """绘制不依赖系统字体或外部资源的轻量操作图标。"""

    pixmap = QPixmap(QSize(18, 18))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    if kind == "edit":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(
            QPolygonF(
                (
                    QPointF(5.0, 12.5),
                    QPointF(11.5, 6.0),
                    QPointF(14.0, 8.5),
                    QPointF(7.5, 15.0),
                )
            )
        )
        painter.drawPolygon(
            QPolygonF(
                (
                    QPointF(3.5, 16.5),
                    QPointF(5.0, 12.5),
                    QPointF(7.5, 15.0),
                )
            )
        )
    else:
        painter.drawLine(QPointF(4.0, 5.5), QPointF(14.0, 5.5))
        painter.drawLine(QPointF(7.0, 3.5), QPointF(11.0, 3.5))
        painter.drawRoundedRect(QRectF(5.0, 6.5, 8.0, 8.5), 1.0, 1.0)
        painter.drawLine(QPointF(8.0, 8.5), QPointF(8.0, 13.0))
        painter.drawLine(QPointF(10.0, 8.5), QPointF(10.0, 13.0))

    painter.end()
    return QIcon(pixmap)


class _ElidedLabel(QLabel):
    """按实际宽度右侧省略，同时保留完整文本用于布局与提示。"""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self._full_text = ""
        self.set_full_text(text)

    @property
    def full_text(self) -> str:
        return self._full_text

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.updateGeometry()
        self.refresh_elision()

    def refresh_elision(self) -> None:
        available_width = self.contentsRect().width()
        displayed_text = self._full_text
        if available_width > 0:
            displayed_text = self.fontMetrics().elidedText(
                self._full_text,
                Qt.TextElideMode.ElideRight,
                available_width,
            )

        if QLabel.text(self) != displayed_text:
            QLabel.setText(self, displayed_text)
        self.setToolTip(self._full_text if displayed_text != self._full_text else "")

    def sizeHint(self) -> QSize:  # noqa: N802
        size_hint = super().sizeHint()
        if not self._full_text:
            return size_hint

        margins = self.contentsMargins()
        full_text_width = (
            self.fontMetrics().horizontalAdvance(self._full_text)
            + margins.left()
            + margins.right()
            + (self.margin() * 2)
        )
        return QSize(max(size_hint.width(), full_text_width), size_hint.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        size_hint = super().minimumSizeHint()
        return QSize(self.minimumWidth(), size_hint.height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.refresh_elision()


class TodoItemWidget(QFrame):
    """待办事项卡片。"""

    request_edit = Signal(object)
    request_delete = Signal(object)
    request_toggle_complete = Signal(object)

    def __init__(
        self, todo_item: dict, parent: Optional[QWidget] = None, *, palette: Optional[ThemeColors] = None
    ):
        super().__init__(parent)
        self.todo_item = todo_item
        self.original_text = todo_item.get("text", "无内容")
        self._theme_manager = get_theme_manager()
        self._palette: ThemeColors = palette or self._theme_manager.current_palette
        self._build_ui()
        self.apply_palette(self._palette)

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setObjectName("TodoItemWidget")
        self.setMinimumHeight(92)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        self.complete_button = QPushButton()
        self.complete_button.setObjectName("TodoCompleteButton")
        self.complete_button.setCheckable(True)
        self.complete_button.setChecked(self.todo_item.get("completed", False))
        icon_path = DONE_ICON_PATH if self.todo_item.get("completed", False) else INCOMPLETE_ICON_PATH
        fallback_char = "✓" if self.todo_item.get("completed", False) else "○"
        self.complete_button.setIcon(get_icon(icon_path, fallback_char))
        self.complete_button.setIconSize(QSize(20, 20))
        self.complete_button.setToolTip("标记为完成/未完成")
        self.complete_button.clicked.connect(self._toggle_complete)
        main_layout.addWidget(self.complete_button)

        self.content_container = QWidget()
        self.content_container.setMinimumWidth(150)
        self.content_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        self.task_text_label = QLabel(self.original_text)
        self.task_text_label.setWordWrap(False)
        self.task_text_label.setMinimumWidth(150)
        self.task_text_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        font = QFont("Segoe UI", 11)
        font.setBold(not self.todo_item.get("completed", False))
        self.task_text_label.setFont(font)

        priority = self.todo_item.get("priority", "中")
        self.priority_label = QLabel(priority)
        self.priority_label.setTextFormat(Qt.TextFormat.RichText)
        content_layout.addWidget(self.task_text_label)
        content_layout.addWidget(self.priority_label)
        main_layout.addWidget(self.content_container, 1)

        self.timer_display_label = _ElidedLabel("无计时")
        self.timer_display_label.setMinimumWidth(50)
        self.timer_display_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self.timer_display_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        main_layout.addWidget(self.timer_display_label)

        self.actions_container = QWidget(self)
        self.actions_container.setObjectName("TodoActionsContainer")
        self.actions_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        actions_layout = QVBoxLayout(self.actions_container)
        actions_layout.setContentsMargins(4, 3, 4, 3)
        actions_layout.setSpacing(2)

        self.edit_button = QPushButton()
        self.edit_button.setObjectName("TodoEditButton")
        self.edit_button.setIconSize(QSize(18, 18))
        self.edit_button.setToolTip("编辑任务")
        self.edit_button.setAccessibleName("编辑任务")
        self.edit_button.clicked.connect(self._edit_item)

        self.delete_button = QPushButton()
        self.delete_button.setObjectName("TodoDeleteButton")
        self.delete_button.setIconSize(QSize(18, 18))
        self.delete_button.setToolTip("删除任务")
        self.delete_button.setAccessibleName("删除任务")
        self.delete_button.clicked.connect(self._delete_item)

        for button in (self.edit_button, self.delete_button):
            button.setMinimumWidth(28)
            button.setFixedHeight(26)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        actions_layout.addWidget(self.edit_button)
        actions_layout.addWidget(self.delete_button)
        actions_layout.addStretch()

        self.actions_container.setFixedWidth(38)
        self.actions_container.hide()

        self.update_timer_display(datetime.now(timezone.utc))
        self.update_text_display()

    def apply_palette(self, palette: ThemeColors) -> None:
        """应用指定主题配色。"""

        self._palette = palette
        self.edit_button.setIcon(_build_action_icon("edit", palette.action_icon))
        self.delete_button.setIcon(_build_action_icon("delete", palette.action_icon))
        self._update_frame_background()
        is_completed = self.todo_item.get("completed", False)
        font = self.task_text_label.font()
        font.setBold(not is_completed)
        self.task_text_label.setFont(font)
        text_decoration = "text-decoration: line-through;" if is_completed else "text-decoration: none;"
        text_color = palette.text_completed if is_completed else palette.text_primary
        self.task_text_label.setStyleSheet(f"color: {text_color}; {text_decoration}")

        self.priority_label.setText(self._priority_badge_html(self.todo_item.get("priority", "中")))
        self.priority_label.setTextFormat(Qt.TextFormat.RichText)

        self.timer_display_label.setStyleSheet(
            f"font-size: 9pt; color: {palette.text_secondary}; {text_decoration}"
        )
        self.update_timer_display(datetime.now(timezone.utc))

    def _update_frame_background(self) -> None:
        is_completed = self.todo_item.get("completed", False)
        bg_color = self._palette.completed_item_bg if is_completed else self._palette.primary_item_bg
        self.setStyleSheet(
            f"""
            QFrame#TodoItemWidget {{
                background-color: {bg_color}; border: 1px solid {self._palette.card_border};
                border-radius: 7px; padding: 12px;
            }}
            QLabel {{ background-color: transparent; }}
            QWidget#TodoActionsContainer {{
                background-color: {self._palette.action_overlay_bg};
                border: 1px solid {self._palette.card_border};
                border-radius: 5px;
            }}
            QPushButton#TodoCompleteButton {{
                background-color: transparent; border: none; border-radius: 5px; padding: 4px;
            }}
            QPushButton#TodoCompleteButton:hover {{
                background-color: {self._palette.action_edit_hover_bg};
            }}
            QPushButton#TodoEditButton,
            QPushButton#TodoDeleteButton {{
                background-color: {self._palette.action_button_bg};
                border: 1px solid {self._palette.action_button_border};
                border-radius: 4px;
                padding: 0px;
            }}
            QPushButton#TodoEditButton:hover,
            QPushButton#TodoEditButton:focus {{
                background-color: {self._palette.action_edit_hover_bg};
                border-color: {self._palette.accent};
            }}
            QPushButton#TodoEditButton:pressed {{
                background-color: {self._palette.action_edit_pressed_bg};
            }}
            QPushButton#TodoDeleteButton:hover,
            QPushButton#TodoDeleteButton:focus {{
                background-color: {self._palette.action_delete_hover_bg};
                border-color: {self._palette.due_critical};
            }}
            QPushButton#TodoDeleteButton:pressed {{
                background-color: {self._palette.action_delete_pressed_bg};
            }}
            """
        )

    def _priority_badge_html(self, priority: str) -> str:
        colors = {
            "高": (self._palette.priority_high, self._palette.priority_high_bg),
            "中": (self._palette.priority_medium, self._palette.priority_medium_bg),
            "低": (self._palette.priority_low, self._palette.priority_low_bg),
        }
        text_color, background = colors.get(
            priority,
            (self._palette.text_primary, self._palette.secondary_background),
        )
        return (
            "<span style='color:{text}; background-color:{bg}; padding:2px 6px; "
            "border-radius:3px; font-size:8pt;'>{content}</span>"
        ).format(text=text_color, bg=background, content=priority)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self._position_actions_overlay()
        self.actions_container.show()
        self.actions_container.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self.actions_container.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_actions_overlay()
        self.timer_display_label.refresh_elision()
        self.update_text_display()

    def _position_actions_overlay(self) -> None:
        content_rect = self.contentsRect()
        overlay_width = min(self.actions_container.width(), content_rect.width())
        self.actions_container.setGeometry(
            content_rect.right() - overlay_width + 1,
            content_rect.top(),
            overlay_width,
            content_rect.height(),
        )
        self.actions_container.raise_()

    def update_text_display(self) -> None:
        layout = self.layout()
        if layout is not None:
            layout.activate()
        content_layout = self.content_container.layout()
        if content_layout is not None:
            content_layout.activate()
        self.timer_display_label.refresh_elision()

        available_width = self.task_text_label.contentsRect().width()
        if available_width <= 0:
            return

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

    def _set_timer_text(self, text: str) -> None:
        self.timer_display_label.set_full_text(text)

    def update_timer_display(self, current_time_utc: datetime) -> None:
        is_completed = self.todo_item.get("completed", False)
        self.complete_button.setChecked(is_completed)
        icon_path = DONE_ICON_PATH if is_completed else INCOMPLETE_ICON_PATH
        fallback_char = "✓" if is_completed else "○"
        self.complete_button.setIcon(get_icon(icon_path, fallback_char))
        self._update_frame_background()

        text_color = self._palette.text_completed if is_completed else self._palette.text_primary
        text_decoration = "text-decoration: line-through;" if is_completed else "text-decoration: none;"
        self.task_text_label.setStyleSheet(f"color: {text_color}; {text_decoration}")
        font = self.task_text_label.font()
        font.setBold(not is_completed)
        self.task_text_label.setFont(font)
        base_timer_color = self._palette.text_completed if is_completed else self._palette.text_secondary
        self.timer_display_label.setStyleSheet(
            f"font-size: 9pt; color: {base_timer_color}; {text_decoration}"
        )

        if is_completed:
            self._set_timer_text("已完成")
            self.timer_display_label.setStyleSheet(
                f"font-size: 9pt; color: {self._palette.text_completed}; font-style: italic; {text_decoration}"
            )
            self.update_text_display()
            return

        snooze_until_str = self.todo_item.get("snoozeUntil")
        if snooze_until_str:
            try:
                snooze_until_dt = datetime.fromisoformat(snooze_until_str.replace("Z", "+00:00"))
                if snooze_until_dt > current_time_utc:
                    self._set_timer_text(
                        f"推迟: {self._format_timedelta(snooze_until_dt - current_time_utc)}"
                    )
                    self.timer_display_label.setStyleSheet(
                        f"font-size: 9pt; color: {self._palette.snooze_badge};"
                    )
                    self.update_text_display()
                    return
            except ValueError:
                print(f"任务 '{self.todo_item.get('text', '')}' 的推迟日期格式错误: {snooze_until_str}")
                self.todo_item["snoozeUntil"] = None

        due_date_str = self.todo_item.get("dueDate")
        if not due_date_str:
            self._set_timer_text("无截止日期")
            self.timer_display_label.setStyleSheet(
                f"font-size: 9pt; color: {self._palette.text_secondary};"
            )
            self.update_text_display()
            return

        try:
            due_date_dt = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        except ValueError:
            self._set_timer_text("日期格式错误!")
            self.timer_display_label.setStyleSheet(
                f"font-size: 9pt; color: {self._palette.due_critical}; font-weight: bold;"
            )
            self.update_text_display()
            return

        diff = due_date_dt - current_time_utc
        time_left_str = self._format_timedelta(diff)
        if diff.total_seconds() <= 0:
            self._set_timer_text(f"已到期 ({time_left_str.replace('-', '')})")
            self.timer_display_label.setStyleSheet(
                f"font-size: 10pt; color: {self._palette.due_critical}; font-weight: bold;"
            )
        else:
            self._set_timer_text(f"剩余: {time_left_str}")
            color = self._palette.due_warning if diff.total_seconds() < 86400 else self._palette.timer_positive
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
