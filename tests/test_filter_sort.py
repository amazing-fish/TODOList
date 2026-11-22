"""筛选、排序与视图状态持久化测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from todo_app.main_window import ModernTodoAppWindow  # noqa: E402


def _make_todo(
    todo_id: int,
    text: str,
    *,
    completed: bool = False,
    priority: str = "中",
    due_date: str | None = None,
    created_at: str = "2026-09-01T00:00:00+00:00",
) -> dict[str, object]:
    return {
        "id": todo_id,
        "text": text,
        "completed": completed,
        "priority": priority,
        "dueDate": due_date,
        "createdAt": created_at,
        "reminderOffset": 0,
        "snoozeUntil": None,
        "lastNotifiedAt": None,
        "notifiedForReminder": False,
        "notifiedForDue": False,
    }


class FilterSortPersistenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _create_window(self, todos: list[dict], store: dict | None = None) -> ModernTodoAppWindow:
        backing = {} if store is None else store
        settings = MagicMock()
        settings.value.side_effect = lambda key, default=None: backing.get(key, default)
        settings.setValue.side_effect = lambda key, val: backing.__setitem__(key, val)
        with (
            patch("todo_app.main_window.load_todos", return_value=todos),
            patch("todo_app.main_window.save_todos"),
            patch("todo_app.main_window.QSettings", return_value=settings),
        ):
            window = ModernTodoAppWindow()
        window.master_timer.stop()
        self.addCleanup(self._close_window, window)
        return window

    @staticmethod
    def _close_window(window: ModernTodoAppWindow) -> None:
        window._quitting_app = True
        window.tray_icon.hide()
        window.close()
        window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()

    def test_due_far_to_near_keeps_incomplete_first_and_no_due_last(self) -> None:
        now = datetime.now(timezone.utc)
        todos = [
            _make_todo(1, "已完成远期", completed=True, due_date=(now + timedelta(days=10)).isoformat()),
            _make_todo(2, "未完成近期", due_date=(now + timedelta(hours=2)).isoformat()),
            _make_todo(3, "未完成远期", due_date=(now + timedelta(days=5)).isoformat()),
            _make_todo(4, "未完成无截止", due_date=None),
        ]
        window = self._create_window(todos)
        window.sort_combo.setCurrentText("截止日期 (远->近)")

        ordered_ids = [
            window.list_widget.itemWidget(window.list_widget.item(i)).todo_item["id"]
            for i in range(window.list_widget.count())
        ]
        self.assertEqual(ordered_ids, [3, 2, 4, 1])

    def test_created_sort_puts_completed_tasks_at_bottom(self) -> None:
        todos = [
            _make_todo(1, "较新已完成", completed=True, created_at="2026-09-03T00:00:00+00:00"),
            _make_todo(2, "较旧未完成", completed=False, created_at="2026-09-01T00:00:00+00:00"),
            _make_todo(3, "较新未完成", completed=False, created_at="2026-09-02T00:00:00+00:00"),
        ]
        window = self._create_window(todos)

        ordered_ids = [
            window.list_widget.itemWidget(window.list_widget.item(i)).todo_item["id"]
            for i in range(window.list_widget.count())
        ]
        self.assertEqual(ordered_ids, [3, 2, 1])

    def test_today_filter_includes_overdue_and_overdue_filter_matches_only_due(self) -> None:
        now = datetime.now(timezone.utc)
        todos = [
            _make_todo(1, "昨日逾期", due_date=(now - timedelta(days=1)).isoformat()),
            _make_todo(2, "即将到期", due_date=(now + timedelta(minutes=10)).isoformat()),
            _make_todo(3, "后天到期", due_date=(now + timedelta(days=2)).isoformat()),
            _make_todo(4, "已完成逾期", completed=True, due_date=(now - timedelta(days=1)).isoformat()),
        ]
        window = self._create_window(todos)

        window.filter_combo.setCurrentText("今天到期")
        today_ids = {
            window.list_widget.itemWidget(window.list_widget.item(i)).todo_item["id"]
            for i in range(window.list_widget.count())
        }
        self.assertIn(1, today_ids)
        self.assertNotIn(3, today_ids)
        self.assertNotIn(4, today_ids)

        window.filter_combo.setCurrentText("已逾期")
        overdue_ids = [
            window.list_widget.itemWidget(window.list_widget.item(i)).todo_item["id"]
            for i in range(window.list_widget.count())
        ]
        self.assertEqual(overdue_ids, [1])

    def test_filter_and_sort_selection_persist_across_restarts(self) -> None:
        store: dict[str, object] = {}
        first = self._create_window([], store=store)
        first.filter_combo.setCurrentText("未完成")
        first.sort_combo.setCurrentText("优先级 (高->低)")
        first.save_geometry_and_state()

        self.assertEqual(store["filterOption"], "未完成")
        self.assertEqual(store["sortOption"], "优先级 (高->低)")

        second = self._create_window([], store=store)
        self.assertEqual(second.filter_combo.currentText(), "未完成")
        self.assertEqual(second.sort_combo.currentText(), "优先级 (高->低)")

    def test_empty_filter_message_distinguishes_filtered_empty_from_total_empty(self) -> None:
        todos = [_make_todo(1, "普通任务", completed=False, priority="中")]
        window = self._create_window(todos)
        window.filter_combo.setCurrentText("高优先级")
        self.assertEqual(window._empty_placeholder_label.text(), "当前「高优先级」下暂无任务")


if __name__ == "__main__":
    unittest.main()
