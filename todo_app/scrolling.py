"""任务列表的滚轮缓动，像素手势仍直接跟随输入。"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, Qt, QVariantAnimation
from PySide6.QtWidgets import QApplication, QListWidget


class SmoothScrollListWidget(QListWidget):
    """用字体行高定义滚轮步长，避免步长随任务卡片高度变化。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._scroll_target = 0.0
        self._applying_scroll = False
        self._scroll_animation = QVariantAnimation(self)
        self._scroll_animation.setDuration(150)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_animation.valueChanged.connect(self._apply_scroll_value)
        scrollbar = self.verticalScrollBar()
        scrollbar.setSingleStep(self.fontMetrics().lineSpacing())
        scrollbar.valueChanged.connect(self._on_scroll_value_changed)
        scrollbar.rangeChanged.connect(self.stop_scrolling)
        scrollbar.sliderPressed.connect(self.stop_scrolling)
        scrollbar.actionTriggered.connect(self.stop_scrolling)
        scrollbar.installEventFilter(self)

    def stop_scrolling(self) -> None:
        """让筛选、列表协调或用户直接定位接管滚动位置。"""

        self._scroll_animation.stop()
        self._scroll_target = float(self.verticalScrollBar().value())

    def _apply_scroll_value(self, value) -> None:
        self._applying_scroll = True
        try:
            self.verticalScrollBar().setValue(round(value))
        finally:
            self._applying_scroll = False

    def _on_scroll_value_changed(self, value: int) -> None:
        if not self._applying_scroll:
            self.stop_scrolling()

    def _scroll_wheel(self, event) -> bool:
        if event.modifiers() != Qt.KeyboardModifier.NoModifier:
            self.stop_scrolling()
            return False
        pixels = event.pixelDelta()
        angle = event.angleDelta()
        if not pixels.isNull():
            self.stop_scrolling()
            if not pixels.y():
                return False
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - pixels.y()
            )
        elif angle.y() and not angle.x():
            # 系统已提供连续手势或惯性时交还 Qt，保留高精度输入的余量累计。
            if event.phase() != Qt.ScrollPhase.NoScrollPhase:
                self.stop_scrolling()
                return False
            scrollbar = self.verticalScrollBar()
            distance = (
                -angle.y() / 120.0
                * QApplication.wheelScrollLines()
                * self.fontMetrics().lineSpacing()
            )
            pending = self._scroll_target - scrollbar.value()
            if pending * distance < 0:
                self._scroll_target = float(scrollbar.value())
            self._scroll_target = min(
                max(self._scroll_target + distance, scrollbar.minimum()),
                scrollbar.maximum(),
            )
            self._scroll_animation.stop()
            self._scroll_animation.setStartValue(float(scrollbar.value()))
            self._scroll_animation.setEndValue(float(self._scroll_target))
            self._scroll_animation.start()
        else:
            self.stop_scrolling()
            return False
        event.accept()
        return True

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self._scroll_wheel(event):
            super().wheelEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.verticalScrollBar():
            if event.type() == QEvent.Type.MouseButtonPress:
                self.stop_scrolling()
            elif event.type() == QEvent.Type.Wheel and self._scroll_wheel(event):
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        self.stop_scrolling()
        super().keyPressEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.stop_scrolling()
        super().hideEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self.verticalScrollBar().setSingleStep(self.fontMetrics().lineSpacing())
