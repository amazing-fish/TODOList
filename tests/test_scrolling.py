"""滚轮与像素手势行为；手动推进动画时钟，不依赖睡眠。"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidgetItem

from todo_app.scrolling import SmoothScrollListWidget


class SmoothScrollingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.widget = SmoothScrollListWidget()
        self.widget.resize(320, 400)
        for index in range(100):
            item = QListWidgetItem(str(index), self.widget)
            item.setSizeHint(QSize(200, 100 if index % 2 else 600))
        self.widget.show()
        self.app.processEvents()
        self.addCleanup(self.widget.close)
        self.bar = self.widget.verticalScrollBar()
        self.animation = self.widget._scroll_animation
        self.step = self.widget.fontMetrics().lineSpacing() * QApplication.wheelScrollLines()

    def wheel(self, angle=-120, *, pixels=0, phase=Qt.ScrollPhase.NoScrollPhase,
              target=None, horizontal=0) -> None:
        event = QWheelEvent(
            QPointF(10, 10), QPointF(10, 10), QPoint(0, pixels),
            QPoint(horizontal, angle), Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier, phase, False,
        )
        self.app.sendEvent(target or self.widget.viewport(), event)

    def finish(self) -> None:
        self.animation.setCurrentTime(self.animation.duration())

    def test_wheel_moves_through_intermediate_positions_with_fixed_distance(self) -> None:
        self.wheel()
        self.assertEqual(self.bar.value(), 0)
        self.animation.setCurrentTime(self.animation.duration() // 2)
        self.assertGreater(self.bar.value(), 0)
        self.assertLess(self.bar.value(), self.step)
        self.finish()
        self.assertEqual(self.bar.value(), self.step)
        self.assertEqual(self.bar.singleStep(), self.widget.fontMetrics().lineSpacing())

    def test_repeated_and_fractional_wheel_events_accumulate(self) -> None:
        for _ in range(8):
            self.wheel(-30)
        self.finish()
        self.assertEqual(self.bar.value(), self.step * 2)

    def test_direction_reversal_takes_effect_from_current_position(self) -> None:
        self.bar.setValue(300)
        self.wheel()
        self.animation.setCurrentTime(50)
        position = self.bar.value()
        self.wheel(120)
        self.finish()
        self.assertEqual(self.bar.value(), position - self.step)

    def test_pixel_gesture_cancels_animation_and_follows_pixels_immediately(self) -> None:
        self.wheel()
        self.wheel(pixels=-17, phase=Qt.ScrollPhase.ScrollUpdate)
        self.assertEqual(self.bar.value(), 17)
        self.assertEqual(self.animation.state(), QAbstractAnimation.State.Stopped)
        self.wheel(pixels=7, phase=Qt.ScrollPhase.ScrollMomentum)
        self.assertEqual(self.bar.value(), 10)

    def test_phased_angle_gesture_does_not_add_inertia(self) -> None:
        self.wheel(phase=Qt.ScrollPhase.ScrollUpdate)
        self.assertEqual(self.bar.value(), self.step)
        self.assertEqual(self.animation.state(), QAbstractAnimation.State.Stopped)

    def test_direct_position_change_cancels_pending_motion(self) -> None:
        self.wheel()
        self.bar.setValue(300)
        self.assertEqual(self.animation.state(), QAbstractAnimation.State.Stopped)
        self.wheel()
        self.finish()
        self.assertEqual(self.bar.value(), 300 + self.step)

    def test_scrollbar_drag_keyboard_hide_and_range_change_stop_animation(self) -> None:
        for action in (
            lambda: QTest.mousePress(self.bar, Qt.MouseButton.LeftButton),
            lambda: QTest.keyClick(self.widget, Qt.Key.Key_PageDown),
            lambda: self.bar.setRange(0, self.bar.maximum() - 1),
            self.widget.hide,
        ):
            with self.subTest(action=action):
                self.wheel()
                action()
                self.assertEqual(self.animation.state(), QAbstractAnimation.State.Stopped)
                QTest.mouseRelease(self.bar, Qt.MouseButton.LeftButton)

    def test_wheel_over_scrollbar_uses_same_animation(self) -> None:
        self.wheel(target=self.bar)
        self.assertEqual(self.bar.value(), 0)
        self.finish()
        self.assertEqual(self.bar.value(), self.step)

    def test_range_edges_do_not_leave_a_pending_overshoot(self) -> None:
        self.bar.setValue(self.bar.maximum() - 2)
        self.wheel()
        self.finish()
        self.assertEqual(self.bar.value(), self.bar.maximum())
        self.wheel(120)
        self.finish()
        self.assertEqual(self.bar.value(), self.bar.maximum() - self.step)
        self.bar.setValue(2)
        self.wheel(120)
        self.finish()
        self.assertEqual(self.bar.value(), 0)

    def test_horizontal_wheel_does_not_move_vertical_scrollbar(self) -> None:
        self.wheel(0, horizontal=-120)
        self.assertEqual(self.bar.value(), 0)
        self.assertEqual(self.animation.state(), QAbstractAnimation.State.Stopped)


if __name__ == "__main__":
    unittest.main()
