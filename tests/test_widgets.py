"""待办卡片布局与交互测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF  # noqa: E402
from PySide6.QtGui import QEnterEvent, QFont, QFontMetrics  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from todo_app.widgets import TodoItemWidget  # noqa: E402
from todo_app.utils import truncate_text_for_width  # noqa: E402


class TodoItemWidgetLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_hover_keeps_text_clear_and_content_geometry_stable(self) -> None:
        host = QWidget()
        host_layout = QVBoxLayout(host)
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": "这是一段很长很长的任务文字，用于检查窄窗口下的显示效果",
                "priority": "中",
                "completed": False,
                "dueDate": None,
            }
        )
        widget.setFixedSize(240, 110)
        host_layout.addWidget(widget)
        host.setFixedSize(262, 132)
        host.show()
        self.addCleanup(host.close)
        self.app.processEvents()

        idle_task_geometry = widget.task_text_label.geometry()
        idle_timer_geometry = widget.timer_display_label.geometry()
        self._assert_displayed_text_fits(widget)

        widget.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()

        self.assertTrue(widget.edit_button.isVisible())
        self.assertTrue(widget.delete_button.isVisible())
        self.assertEqual(widget.task_text_label.geometry(), idle_task_geometry)
        self.assertEqual(widget.timer_display_label.geometry(), idle_timer_geometry)
        self._assert_displayed_text_fits(widget)

        widget.leaveEvent(QEvent(QEvent.Type.Leave))
        self.app.processEvents()
        self.assertFalse(widget.edit_button.isVisible())
        self.assertFalse(widget.delete_button.isVisible())
        self.assertEqual(widget.task_text_label.geometry(), idle_task_geometry)
        self.assertEqual(widget.timer_display_label.geometry(), idle_timer_geometry)

    def test_short_text_is_elided_instead_of_overflowing(self) -> None:
        font = QFont("Segoe UI", 11)
        metrics = QFontMetrics(font)
        max_width = metrics.horizontalAdvance("这…")

        displayed = truncate_text_for_width(
            "六个字符宽度", font, max_width, min_chars=6
        )

        self.assertLessEqual(metrics.horizontalAdvance(displayed), max_width)
        self.assertNotEqual(displayed, "六个字符宽度")

    def test_timer_text_growth_reelides_task_after_layout_change(self) -> None:
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
        host = QWidget()
        host_layout = QVBoxLayout(host)
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": "这是一段很长的任务文字",
                "priority": "中",
                "completed": False,
                "dueDate": (now + timedelta(seconds=1)).isoformat(),
            }
        )
        widget.setFixedSize(320, 110)
        host_layout.addWidget(widget)
        host.setFixedSize(342, 132)
        host.show()
        self.addCleanup(host.close)

        widget.update_timer_display(now)
        self.app.processEvents()
        self.assertEqual(widget.timer_display_label.text(), "剩余: 1秒")

        widget.update_timer_display(now + timedelta(days=100_000))
        task_width_when_update_returns = widget.task_text_label.contentsRect().width()
        self.app.processEvents()

        self.assertTrue(widget.timer_display_label.text().startswith("已到期"))
        self.assertEqual(
            task_width_when_update_returns,
            widget.task_text_label.contentsRect().width(),
        )
        self._assert_displayed_text_fits(widget)

    def _assert_displayed_text_fits(self, widget: TodoItemWidget) -> None:
        metrics = QFontMetrics(widget.task_text_label.font())
        self.assertLessEqual(
            metrics.horizontalAdvance(widget.task_text_label.text()),
            widget.task_text_label.contentsRect().width(),
        )


if __name__ == "__main__":
    unittest.main()
