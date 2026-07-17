"""待办卡片布局与交互测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF  # noqa: E402
from PySide6.QtGui import QEnterEvent, QFont, QFontMetrics  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QVBoxLayout,
    QWidget,
)

from todo_app.main_window import ModernTodoAppWindow  # noqa: E402
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


class TodoListCardIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_default_width_card_uses_viewport_and_hover_actions_overlay_timer(self) -> None:
        window = self._create_window()
        window.resize(320, 640)
        window.show()
        self.app.processEvents()

        item = window.list_widget.item(0)
        card = window.list_widget.itemWidget(item)
        viewport = window.list_widget.viewport()

        self.assertLessEqual(card.width(), viewport.width())
        self.assertLessEqual(
            window.list_widget.visualItemRect(item).right(),
            viewport.rect().right(),
        )
        self.assertEqual(card.task_text_label.minimumWidth(), 150)
        self.assertGreaterEqual(card.task_text_label.width(), 150)
        self.assertEqual(card.timer_display_label.minimumWidth(), 50)
        self.assertGreaterEqual(card.timer_display_label.width(), 50)

        idle_task_geometry = card.task_text_label.geometry()
        idle_timer_geometry = card.timer_display_label.geometry()
        card.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()

        self.assertFalse(card.edit_button.visibleRegion().isEmpty())
        self.assertFalse(card.delete_button.visibleRegion().isEmpty())
        self.assertIs(
            card.childAt(
                card.edit_button.mapTo(card, card.edit_button.rect().center())
            ),
            card.edit_button,
        )
        self.assertIs(
            card.childAt(
                card.delete_button.mapTo(card, card.delete_button.rect().center())
            ),
            card.delete_button,
        )
        self.assertTrue(
            card.actions_container.geometry().intersects(
                card.timer_display_label.geometry()
            )
        )
        self.assertEqual(card.task_text_label.geometry(), idle_task_geometry)
        self.assertEqual(card.timer_display_label.geometry(), idle_timer_geometry)

    def test_todo_list_disables_item_selection_frame(self) -> None:
        window = self._create_window()

        self.assertEqual(
            window.list_widget.selectionMode(),
            QAbstractItemView.SelectionMode.NoSelection,
        )

    def test_vertical_scrollbar_is_compact_and_right_aligned(self) -> None:
        window = self._create_window(todo_count=10)
        window.resize(320, 640)
        window.show()
        self.app.processEvents()

        scrollbar = window.list_widget.verticalScrollBar()
        central_widget = window.centralWidget()

        self.assertTrue(scrollbar.isVisible())
        self.assertEqual(scrollbar.width(), 8)
        self.assertEqual(
            scrollbar.mapTo(
                window.list_widget, QPoint(scrollbar.width(), 0)
            ).x()
            - 1,
            window.list_widget.contentsRect().right(),
        )

        list_left = window.list_widget.mapTo(central_widget, QPoint(0, 0)).x()
        scrollbar_right = scrollbar.mapTo(
            central_widget, QPoint(scrollbar.width(), 0)
        ).x()
        scrollbar_right_spacing = central_widget.width() - scrollbar_right
        self.assertEqual(scrollbar_right_spacing, 7)
        self.assertEqual(
            list_left,
            scrollbar.width() + scrollbar_right_spacing,
        )

        add_button_right = window.add_button.mapTo(
            central_widget, QPoint(window.add_button.width(), 0)
        ).x()
        self.assertEqual(
            list_left,
            central_widget.width() - add_button_right,
        )

        item = window.list_widget.item(0)
        card = window.list_widget.itemWidget(item)
        self.assertLessEqual(card.width(), window.list_widget.viewport().width())
        self.assertEqual(
            window.list_widget.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )

    def _create_window(self, todo_count: int = 1) -> ModernTodoAppWindow:
        todo = {
            "id": 1,
            "text": "这是一段很长很长的任务文字，用于检查窄窗口下的显示效果",
            "priority": "中",
            "completed": False,
            "dueDate": (
                datetime.now(timezone.utc) + timedelta(days=123)
            ).isoformat(),
            "createdAt": "2026-07-17T00:00:00+00:00",
            "snoozeUntil": None,
        }
        todos = [{**todo, "id": index + 1} for index in range(todo_count)]
        load_patcher = patch("todo_app.main_window.load_todos", return_value=todos)
        load_patcher.start()
        self.addCleanup(load_patcher.stop)
        window = ModernTodoAppWindow()
        window.master_timer.stop()
        self.addCleanup(self._close_window, window)
        return window

    @staticmethod
    def _close_window(window: ModernTodoAppWindow) -> None:
        window.master_timer.stop()
        window._quitting_app = True
        window.tray_icon.hide()
        window.close()


if __name__ == "__main__":
    unittest.main()
