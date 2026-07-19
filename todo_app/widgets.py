"""自定义部件。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal, QEvent, QPoint, QPointF, QRect, QRectF
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
    QTextOption,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    DONE_ICON_PATH,
    INCOMPLETE_ICON_PATH,
)
from .utils import get_icon
from .theme import ThemeColors, get_theme_manager


_TASK_LINE_BREAKS = re.compile(r"\r\n|\r|\n")
_TASK_AREA_FLOOR_WIDTH = 40
_TASK_AREA_MAX_MINIMUM_WIDTH = 150
_TASK_DETAILS_MAX_WIDTH = 360
_TASK_DETAILS_MIN_TEXT_WIDTH = 160
_TASK_DETAILS_HORIZONTAL_MARGIN = 12
_TASK_DETAILS_VERTICAL_MARGIN = 10
_TASK_DETAILS_FRAME_WIDTH = 2
_TASK_DETAILS_GAP = 6
_TASK_DETAILS_MIN_VERTICAL_SPACE = 120


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


class _PerLineElidedTaskLabel(QLabel):
    """保留用户换行，并让每个逻辑行独立执行末尾省略。"""

    details_requested = Signal()
    details_dismissed = Signal()
    details_requirement_changed = Signal(bool)
    details_scroll_requested = Signal(int)

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._is_elided = False
        self._is_hovered = False
        self.setMouseTracking(True)
        self.refresh_elision()

    def logical_lines(self) -> list[str]:
        return _TASK_LINE_BREAKS.split(self.text())

    def _available_width(self) -> int:
        return max(self.contentsRect().width() - (self.margin() * 2), 0)

    def displayed_lines(self) -> list[str]:
        logical_lines = self.logical_lines()
        available_width = self._available_width()
        if available_width <= 0:
            return logical_lines

        metrics = self.fontMetrics()
        return [
            metrics.elidedText(
                line,
                Qt.TextElideMode.ElideRight,
                available_width,
            )
            for line in logical_lines
        ]

    def needs_details(self) -> bool:
        """返回当前几何下是否需要完整正文详情。"""

        return self._is_elided or len(self.logical_lines()) > 1

    def is_hovered(self) -> bool:
        """返回鼠标是否仍停留在正文区域。"""

        return self._is_hovered

    def natural_width(self) -> int:
        metrics = self.fontMetrics()
        widest_line = max(
            (metrics.horizontalAdvance(line) for line in self.logical_lines()),
            default=0,
        )
        margins = self.contentsMargins()
        return (
            widest_line
            + margins.left()
            + margins.right()
            + (self.margin() * 2)
        )

    def refresh_elision(self) -> None:
        previously_required = self.needs_details()
        displayed_lines = self.displayed_lines()
        self._is_elided = any(
            displayed != original
            for displayed, original in zip(displayed_lines, self.logical_lines())
        )
        # 详情由卡片的主题化浮层负责，避免 Qt 原生 tooltip 重复出现。
        self.setToolTip("")
        currently_required = self.needs_details()
        if currently_required != previously_required:
            self.details_requirement_changed.emit(currently_required)
        self.update()

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        del width
        margins = self.contentsMargins()
        return (
            len(self.logical_lines()) * self.fontMetrics().lineSpacing()
            + margins.top()
            + margins.bottom()
            + (self.margin() * 2)
        )

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.natural_width(), self.heightForWidth(self.natural_width()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, self.heightForWidth(0))

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        del event
        content_rect = self.contentsRect().adjusted(
            self.margin(),
            self.margin(),
            -self.margin(),
            -self.margin(),
        )
        painter = QPainter(self)
        painter.setClipRect(content_rect)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        text_option = QTextOption()
        text_option.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        text_option.setWrapMode(QTextOption.WrapMode.NoWrap)
        line_height = self.fontMetrics().lineSpacing()
        for index, line in enumerate(self.displayed_lines()):
            line_rect = QRectF(
                content_rect.left(),
                content_rect.top() + (index * line_height),
                content_rect.width(),
                line_height,
            )
            painter.drawText(line_rect, line, text_option)
        painter.end()

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.refresh_elision()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self._is_hovered = True
        if self.needs_details():
            self.details_requested.emit()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self._is_hovered = False
        self.details_dismissed.emit()
        super().leaveEvent(event)

    def wheelEvent(self, event: QEvent) -> None:  # noqa: N802
        if self.needs_details() and event.angleDelta().y():
            self.details_scroll_requested.emit(event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)


class _TaskDetailsPopup(QFrame):
    """不抢占焦点的纯文本任务详情浮层。"""

    def __init__(self, parent: QWidget):
        flags = (
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(parent, flags)
        self.setObjectName("TodoTaskDetailsPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMaximumWidth(_TASK_DETAILS_MAX_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            _TASK_DETAILS_HORIZONTAL_MARGIN,
            _TASK_DETAILS_VERTICAL_MARGIN,
            _TASK_DETAILS_HORIZONTAL_MARGIN,
            _TASK_DETAILS_VERTICAL_MARGIN,
        )
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("TodoTaskDetailsScrollArea")
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll_area.verticalScrollBar().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scrollbar_reserve = max(
            8,
            self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent),
        )
        self._content_height = 0

        self.details_label = QLabel()
        self.details_label.setTextFormat(Qt.TextFormat.PlainText)
        self.details_label.setWordWrap(True)
        self.details_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.details_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.details_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )
        self.scroll_area.setWidget(self.details_label)
        layout.addWidget(self.scroll_area)
        self.hide()

    def set_details_text(self, text: str) -> None:
        """保留原文并按最大宽度计算紧凑的自动换行尺寸。"""

        self.details_label.setText(text)
        max_text_width = (
            _TASK_DETAILS_MAX_WIDTH
            - (_TASK_DETAILS_HORIZONTAL_MARGIN * 2)
            - _TASK_DETAILS_FRAME_WIDTH
            - self._scrollbar_reserve
        )
        natural_width = max(
            (
                self.details_label.fontMetrics().horizontalAdvance(line)
                for line in _TASK_LINE_BREAKS.split(text)
            ),
            default=0,
        )
        text_width = min(
            max(natural_width, _TASK_DETAILS_MIN_TEXT_WIDTH),
            max_text_width,
        )
        self.details_label.setFixedWidth(text_width)
        details_height = self.details_label.heightForWidth(text_width)
        self._content_height = max(
            details_height,
            self.details_label.fontMetrics().lineSpacing(),
        )
        self.details_label.setFixedHeight(self._content_height)
        self.scroll_area.setFixedWidth(text_width + self._scrollbar_reserve)
        self.setFixedWidth(
            text_width
            + self._scrollbar_reserve
            + (_TASK_DETAILS_HORIZONTAL_MARGIN * 2)
            + _TASK_DETAILS_FRAME_WIDTH
        )
        self.set_height_limit(
            self._content_height
            + (_TASK_DETAILS_VERTICAL_MARGIN * 2)
            + _TASK_DETAILS_FRAME_WIDTH
        )
        self.scroll_area.verticalScrollBar().setValue(0)

    def set_height_limit(self, maximum_height: int) -> None:
        """限制外框高度，并让超出部分通过滚动视口访问。"""

        frame_height = (
            (_TASK_DETAILS_VERTICAL_MARGIN * 2) + _TASK_DETAILS_FRAME_WIDTH
        )
        viewport_height = min(
            self._content_height,
            max(maximum_height - frame_height, 1),
        )
        self.scroll_area.setFixedHeight(viewport_height)
        self.setFixedHeight(viewport_height + frame_height)

    def scroll_details(self, wheel_delta: int) -> None:
        """在正文保持悬停时用滚轮浏览超长详情。"""

        scrollbar = self.scroll_area.verticalScrollBar()
        step = max(scrollbar.singleStep(), self.details_label.fontMetrics().lineSpacing())
        wheel_steps = max(abs(wheel_delta) // 120, 1)
        direction = -1 if wheel_delta > 0 else 1
        scrollbar.setValue(scrollbar.value() + (direction * wheel_steps * step * 3))

    def apply_palette(self, palette: ThemeColors) -> None:
        """让详情浮层与当前卡片主题保持一致。"""

        self.setStyleSheet(
            f"""
            QFrame#TodoTaskDetailsPopup {{
                background-color: {palette.primary_item_bg};
                border: 1px solid {palette.card_border};
                border-radius: 6px;
            }}
            QFrame#TodoTaskDetailsPopup QLabel {{
                color: {palette.text_primary};
                background-color: transparent;
                font-size: 10pt;
            }}
            QScrollArea#TodoTaskDetailsScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {palette.input_border};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background-color: transparent;
            }}
            """
        )


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
        content_policy = QSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        content_policy.setHeightForWidth(True)
        self.content_container.setSizePolicy(content_policy)
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        self.task_text_label = _PerLineElidedTaskLabel(self.original_text)
        self.task_text_label.setTextFormat(Qt.TextFormat.PlainText)
        self.task_text_label.setWordWrap(False)
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
        self.task_details_popup = _TaskDetailsPopup(self)
        self.task_text_label.details_requested.connect(self._show_task_details)
        self.task_text_label.details_dismissed.connect(self._hide_task_details)
        self.task_text_label.details_requirement_changed.connect(
            self._handle_task_details_requirement
        )
        self.task_text_label.details_scroll_requested.connect(
            self.task_details_popup.scroll_details
        )

        priority = self.todo_item.get("priority", "中")
        self.priority_label = QLabel(priority)
        self.priority_label.setTextFormat(Qt.TextFormat.RichText)
        content_layout.addWidget(self.task_text_label)
        content_layout.addWidget(self.priority_label)
        self._update_task_area_minimum_width()
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
        self.task_details_popup.apply_palette(palette)

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
        self._hide_task_details()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_actions_overlay()
        self.timer_display_label.refresh_elision()
        if self.task_details_popup.isVisible():
            if self.task_text_label.needs_details():
                self._position_task_details_popup()
            else:
                self._hide_task_details()

    def hideEvent(self, event: QEvent) -> None:  # noqa: N802
        self._hide_task_details()
        super().hideEvent(event)

    def _show_task_details(self) -> None:
        if not self.task_text_label.needs_details():
            return
        self.task_details_popup.set_details_text(self.original_text)
        self._position_task_details_popup()
        self.task_details_popup.show()
        self.task_details_popup.raise_()

    def _hide_task_details(self) -> None:
        self.task_details_popup.hide()

    def _handle_task_details_requirement(self, required: bool) -> None:
        if not required:
            self._hide_task_details()
        elif self.task_text_label.is_hovered():
            self._show_task_details()

    def _position_task_details_popup(self) -> None:
        popup = self.task_details_popup
        screen = self.screen()
        if screen is None:
            return

        available = screen.availableGeometry()
        task_origin = self.task_text_label.mapToGlobal(QPoint(0, 0))
        card_rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
        space_below = max(
            available.bottom() - card_rect.bottom() - _TASK_DETAILS_GAP,
            0,
        )
        space_above = max(
            card_rect.top() - available.top() - _TASK_DETAILS_GAP,
            0,
        )
        space_right = max(
            available.right() - card_rect.right() - _TASK_DETAILS_GAP,
            0,
        )
        space_left = max(
            card_rect.left() - available.left() - _TASK_DETAILS_GAP,
            0,
        )

        # 上下空间都过小时优先移到卡片侧面，避免详情覆盖编辑/删除区域。
        if (
            max(space_above, space_below) < _TASK_DETAILS_MIN_VERTICAL_SPACE
            and max(space_left, space_right) >= popup.width()
        ):
            popup.set_height_limit(available.height())
            if space_right >= popup.width():
                popup_x = card_rect.right() + _TASK_DETAILS_GAP + 1
            else:
                popup_x = card_rect.left() - _TASK_DETAILS_GAP - popup.width()
            maximum_y = max(
                available.top(),
                available.bottom() - popup.height() + 1,
            )
            popup_y = min(max(task_origin.y(), available.top()), maximum_y)
            popup.move(popup_x, popup_y)
            return

        show_below = space_below >= space_above
        vertical_space = space_below if show_below else space_above
        popup.set_height_limit(vertical_space)
        maximum_x = max(
            available.left(),
            available.right() - popup.width() + 1,
        )
        popup_x = min(
            max(task_origin.x(), available.left()),
            maximum_x,
        )
        if show_below:
            popup_y = card_rect.bottom() + _TASK_DETAILS_GAP + 1
        else:
            popup_y = card_rect.top() - _TASK_DETAILS_GAP - popup.height()
        popup.move(popup_x, popup_y)

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
        self._update_task_area_minimum_width()
        self.task_text_label.refresh_elision()
        self.task_text_label.updateGeometry()
        self.content_container.updateGeometry()
        self.updateGeometry()
        self.timer_display_label.refresh_elision()

    def _update_task_area_minimum_width(self) -> None:
        natural_width = max(
            self.task_text_label.natural_width(),
            self.priority_label.sizeHint().width(),
        )
        minimum_width = max(
            _TASK_AREA_FLOOR_WIDTH,
            min(_TASK_AREA_MAX_MINIMUM_WIDTH, natural_width),
        )
        self.content_container.setMinimumWidth(minimum_width)
        self.task_text_label.setMinimumWidth(minimum_width)

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
