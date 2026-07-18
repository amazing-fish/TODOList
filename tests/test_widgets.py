"""待办卡片布局与交互测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
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

    def test_timer_status_full_text_is_preserved_for_supported_states(self) -> None:
        now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        cases = (
            ({"completed": True, "dueDate": None}, "已完成"),
            ({"completed": False, "dueDate": None}, "无截止日期"),
            ({"completed": False, "dueDate": "not-a-date"}, "日期格式错误!"),
            (
                {
                    "completed": False,
                    "dueDate": None,
                    "snoozeUntil": (now + timedelta(days=2)).isoformat(),
                },
                "推迟: 2天",
            ),
        )

        for overrides, expected_text in cases:
            with self.subTest(expected_text=expected_text):
                todo = {
                    "id": 1,
                    "text": "检查计时状态",
                    "priority": "中",
                    "completed": False,
                    "dueDate": None,
                    "snoozeUntil": None,
                    **overrides,
                }
                widget = TodoItemWidget(todo)
                widget.setFixedSize(420, 110)
                widget.show()
                self.addCleanup(widget.close)

                with patch("builtins.print"):
                    widget.update_timer_display(now)
                self.app.processEvents()

                self.assertEqual(widget.timer_display_label.full_text, expected_text)
                self.assertEqual(widget.timer_display_label.text(), expected_text)
                self.assertEqual(widget.timer_display_label.toolTip(), "")

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
        for button in (card.edit_button, card.delete_button):
            self.assertGreaterEqual(button.width(), 28)
            self.assertGreaterEqual(button.height(), 26)
            self.assertFalse(button.icon().isNull())
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

    def test_narrow_timer_elides_from_right_and_preserves_status_prefix(self) -> None:
        now = datetime.now(timezone.utc)
        todos = [
            {
                "id": 1,
                "text": "很长的未来任务名称，用于验证窄卡片计时显示",
                "priority": "中",
                "completed": False,
                "dueDate": (now + timedelta(days=123_456)).isoformat(),
                "createdAt": now.isoformat(),
                "snoozeUntil": None,
            },
            {
                "id": 2,
                "text": "很长的逾期任务名称，用于验证窄卡片计时显示",
                "priority": "高",
                "completed": False,
                "dueDate": (now - timedelta(days=123_456)).isoformat(),
                "createdAt": now.isoformat(),
                "snoozeUntil": None,
            },
        ]
        window = self._create_window(todos=todos)
        window.resize(320, 640)
        window.show()
        self.app.processEvents()

        for index, prefix in enumerate(("剩余", "已到期")):
            with self.subTest(prefix=prefix):
                item = window.list_widget.item(index)
                card = window.list_widget.itemWidget(item)
                displayed_text = card.timer_display_label.text()
                available_width = card.timer_display_label.contentsRect().width()

                self.assertLessEqual(card.width(), window.list_widget.viewport().width())
                self.assertTrue(displayed_text.startswith(prefix))
                self.assertTrue(displayed_text.endswith("…"))
                self.assertLessEqual(
                    card.timer_display_label.fontMetrics().horizontalAdvance(displayed_text),
                    available_width,
                )
                self.assertNotEqual(displayed_text, card.timer_display_label.full_text)
                self.assertEqual(
                    card.timer_display_label.toolTip(),
                    card.timer_display_label.full_text,
                )

    def test_multiple_cards_have_real_vertical_gap_with_unpainted_background(self) -> None:
        window = self._create_window(todo_count=2)
        window.resize(320, 640)
        window.show()
        self.app.processEvents()

        first_item = window.list_widget.item(0)
        second_item = window.list_widget.item(1)
        first_card = window.list_widget.itemWidget(first_item)
        second_card = window.list_widget.itemWidget(second_item)
        card_gap = second_card.geometry().top() - first_card.geometry().bottom() - 1

        self.assertEqual(card_gap, 8)
        self.assertGreaterEqual(first_item.sizeHint().height(), first_card.minimumHeight())
        self.assertGreaterEqual(second_item.sizeHint().height(), second_card.minimumHeight())

        viewport_image = window.list_widget.viewport().grab().toImage()
        sample_x = first_card.geometry().center().x()
        card_y = first_card.geometry().top() + 5
        gap_y = first_card.geometry().bottom() + 1 + card_gap // 2
        self.assertNotEqual(
            viewport_image.pixelColor(sample_x, card_y).rgba(),
            viewport_image.pixelColor(sample_x, gap_y).rgba(),
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

    def _create_window(
        self,
        todo_count: int = 1,
        *,
        todos: list[dict] | None = None,
    ) -> ModernTodoAppWindow:
        if todos is None:
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
