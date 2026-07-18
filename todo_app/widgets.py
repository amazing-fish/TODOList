"""自定义部件。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal, QEvent, QPointF, QRectF
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
    QTextDocument,
    QTextOption,
)
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
from .utils import get_icon
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

    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
        *,
        preserved_prefixes: tuple[str, ...] = (),
    ):
        super().__init__("", parent)
        self._full_text = ""
        self._preserved_prefixes = preserved_prefixes
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
            if displayed_text != self._full_text:
                for prefix in self._preserved_prefixes:
                    if not self._full_text.startswith(prefix):
                        continue
                    prefix_width = self.fontMetrics().horizontalAdvance(prefix)
                    suffix = self._full_text[len(prefix) :]
                    suffix_text = self.fontMetrics().elidedText(
                        suffix,
                        Qt.TextElideMode.ElideRight,
                        max(available_width - prefix_width, 0),
                    )
                    if (
                        suffix
                        and not suffix_text.endswith("…")
                        and self.fontMetrics().horizontalAdvance("…")
                        <= available_width - prefix_width
                    ):
                        suffix_text = "…"
                    candidate = prefix + suffix_text
                    if (
                        suffix_text
                        and self.fontMetrics().horizontalAdvance(candidate) <= available_width
                    ):
                        displayed_text = candidate
                    break

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


class _WrappingTaskLabel(QLabel):
    """以一致的 anywhere-wrap 规则测量并绘制纯文本任务正文。"""

    def _document_for_width(self, width: int) -> QTextDocument:
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(self.font())
        text_option = document.defaultTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        document.setDefaultTextOption(text_option)
        document.setPlainText(self.text())
        document.setTextWidth(max(width, 1))
        return document

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        margins = self.contentsMargins()
        inner_width = width - margins.left() - margins.right() - (self.margin() * 2)
        document = self._document_for_width(inner_width)
        return int(document.size().height() + 0.999) + margins.top() + margins.bottom()

    def sizeHint(self) -> QSize:  # noqa: N802
        size_hint = super().sizeHint()
        width = self.width() if self.width() > 0 else size_hint.width()
        return QSize(size_hint.width(), self.heightForWidth(width))

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        del event
        content_rect = self.contentsRect()
        document = self._document_for_width(content_rect.width())
        painter = QPainter(self)
        painter.setClipRect(content_rect)
        painter.translate(content_rect.topLeft())
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(
            QPalette.ColorRole.Text,
            self.palette().color(QPalette.ColorRole.WindowText),
        )
        context.clip = QRectF(0, 0, content_rect.width(), content_rect.height())
        document.documentLayout().draw(painter, context)
        painter.end()


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
        card_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card_policy.setHeightForWidth(True)
        self.setSizePolicy(card_policy)

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
        content_policy = QSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        content_policy.setHeightForWidth(True)
        self.content_container.setSizePolicy(content_policy)
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        self.task_text_label = _WrappingTaskLabel(self.original_text)
        self.task_text_label.setTextFormat(Qt.TextFormat.PlainText)
        self.task_text_label.setWordWrap(True)
        self.task_text_label.setMinimumWidth(150)
        text_policy = QSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        text_policy.setHeightForWidth(True)
        self.task_text_label.setSizePolicy(text_policy)
        font = self.task_text_label.font()
        font.setPointSize(11)
        is_completed = self.todo_item.get("completed", False)
        font.setBold(not is_completed)
        font.setStrikeOut(is_completed)
        self.task_text_label.setFont(font)

        priority = self.todo_item.get("priority", "中")
        self.priority_label = QLabel(priority)
        self.priority_label.setTextFormat(Qt.TextFormat.RichText)
        content_layout.addWidget(self.task_text_label)
        content_layout.addWidget(self.priority_label)
        main_layout.addWidget(self.content_container, 1)

        self.timer_display_label = _ElidedLabel(
            "无计时",
            preserved_prefixes=("剩余", "已到期", "推迟"),
        )
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
        font.setStrikeOut(is_completed)
        self.task_text_label.setFont(font)
        text_decoration = "text-decoration: line-through;" if is_completed else "text-decoration: none;"
        text_color = palette.text_completed if is_completed else palette.text_primary
        self.task_text_label.setStyleSheet(f"color: {text_color}; {text_decoration}")

        self.priority_label.setText(self._priority_badge_html(self.todo_item.get("priority", "中")))
        self.priority_label.setTextFormat(Qt.TextFormat.RichText)

        timer_font = self.timer_display_label.font()
        timer_font.setPointSize(9)
        timer_font.setStrikeOut(is_completed)
        self.timer_display_label.setFont(timer_font)
        self.timer_display_label.setStyleSheet(f"color: {palette.text_secondary};")
        self._update_timer_minimum_width()
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

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        layout = self.layout()
        if layout is None:
            return self.minimumHeight()

        layout_height = layout.heightForWidth(max(width, 0))
        if layout_height < 0:
            layout_height = layout.sizeHint().height()
        return max(self.minimumHeight(), layout_height)

    def requiredHeight(self) -> int:  # noqa: N802
        """根据布局后的真实正文宽度返回完整卡片高度。"""

        main_layout = self.layout()
        content_layout = self.content_container.layout()
        if main_layout is None or content_layout is None:
            return self.minimumHeight()

        main_layout.activate()
        content_layout.activate()
        content_margins = content_layout.contentsMargins()
        text_height = self.task_text_label.heightForWidth(
            self.task_text_label.contentsRect().width()
        )
        priority_height = max(
            self.priority_label.minimumHeight(),
            self.priority_label.sizeHint().height(),
        )
        content_height = (
            content_margins.top()
            + text_height
            + content_layout.spacing()
            + priority_height
            + content_margins.bottom()
        )
        child_height = max(
            content_height,
            self.complete_button.sizeHint().height(),
            self.timer_display_label.sizeHint().height(),
        )
        main_margins = main_layout.contentsMargins()
        frame_vertical_inset = max(0, self.height() - self.contentsRect().height())
        return max(
            self.minimumHeight(),
            frame_vertical_inset
            + main_margins.top()
            + child_height
            + main_margins.bottom(),
        )

    def sizeHint(self) -> QSize:  # noqa: N802
        size_hint = super().sizeHint()
        width = self.width() if self.width() > 0 else size_hint.width()
        return QSize(size_hint.width(), self.heightForWidth(width))

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
        if self.task_text_label.text() != self.original_text:
            self.task_text_label.setText(self.original_text)
        self.task_text_label.setToolTip("")
        self.task_text_label.updateGeometry()
        self.content_container.updateGeometry()
        self.updateGeometry()
        self.timer_display_label.refresh_elision()

    def _toggle_complete(self) -> None:
        self.request_toggle_complete.emit(self.todo_item["id"])

    def _edit_item(self) -> None:
        self.request_edit.emit(self.todo_item["id"])

    def _delete_item(self) -> None:
        self.request_delete.emit(self.todo_item["id"])

    def _set_timer_text(self, text: str) -> None:
        self.timer_display_label.set_full_text(text)

    def _update_timer_minimum_width(self) -> None:
        prefix_width = max(
            self.timer_display_label.fontMetrics().horizontalAdvance(prefix + "…")
            for prefix in ("剩余", "已到期", "推迟")
        )
        self.timer_display_label.setMinimumWidth(max(50, prefix_width))

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
        font.setStrikeOut(is_completed)
        self.task_text_label.setFont(font)
        timer_font = self.timer_display_label.font()
        timer_font.setPointSize(9)
        timer_font.setBold(False)
        timer_font.setItalic(False)
        timer_font.setStrikeOut(is_completed)
        self.timer_display_label.setFont(timer_font)
        self._update_timer_minimum_width()
        base_timer_color = self._palette.text_completed if is_completed else self._palette.text_secondary
        self.timer_display_label.setStyleSheet(f"color: {base_timer_color};")

        if is_completed:
            self._set_timer_text("已完成")
            timer_font.setItalic(True)
            self.timer_display_label.setFont(timer_font)
            self.timer_display_label.setStyleSheet(f"color: {self._palette.text_completed};")
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
                        f"color: {self._palette.snooze_badge};"
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
                f"color: {self._palette.text_secondary};"
            )
            self.update_text_display()
            return

        try:
            due_date_dt = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        except ValueError:
            self._set_timer_text("日期格式错误!")
            timer_font.setBold(True)
            self.timer_display_label.setFont(timer_font)
            self.timer_display_label.setStyleSheet(f"color: {self._palette.due_critical};")
            self.update_text_display()
            return

        diff = due_date_dt - current_time_utc
        time_left_str = self._format_timedelta(diff)
        if diff.total_seconds() <= 0:
            self._set_timer_text(f"已到期 ({time_left_str.replace('-', '')})")
            timer_font.setPointSize(10)
            timer_font.setBold(True)
            self.timer_display_label.setFont(timer_font)
            self._update_timer_minimum_width()
            self.timer_display_label.setStyleSheet(f"color: {self._palette.due_critical};")
        else:
            self._set_timer_text(f"剩余: {time_left_str}")
            color = self._palette.due_warning if diff.total_seconds() < 86400 else self._palette.timer_positive
            timer_font.setBold(True)
            self.timer_display_label.setFont(timer_font)
            self.timer_display_label.setStyleSheet(f"color: {color};")

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
