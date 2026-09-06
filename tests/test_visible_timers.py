"""可见卡片计时刷新与完整提醒扫描的边界。"""
from __future__ import annotations

import os
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from todo_app.fonts import apply_application_font
from todo_app.main_window import ModernTodoAppWindow


class VisibleTimerRefreshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        apply_application_font()

    def setUp(self) -> None:
        self.now = datetime(2026, 9, 7, 8, tzinfo=timezone.utc)
        self.tasks = [
            {
                "id": index, "text": f"任务 {index}", "completed": False,
                "priority": "高" if index == 99 else "中",
                "createdAt": self.now.isoformat(),
                "dueDate": (self.now + timedelta(hours=2)).isoformat(),
                "reminderOffset": -1,
            }
            for index in range(100)
        ]
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        for module in ("todo_app.main_window", "todo_app.widgets"):
            clock = self.patches.enter_context(patch(f"{module}.datetime", wraps=datetime))
            clock.now.side_effect = lambda tz=None: self.now.astimezone(tz) if tz else self.now.replace(tzinfo=None)
        self.patches.enter_context(patch("todo_app.main_window.load_todos", return_value=self.tasks))
        self.save = self.patches.enter_context(patch("todo_app.main_window.save_todos"))
        self.patches.enter_context(patch("todo_app.main_window.QSettings", return_value=MagicMock()))
        self.window = ModernTodoAppWindow()
        self.window.master_timer.stop()
        self.addCleanup(self.close_window)
        self.window.resize(440, 560)
        self.window.show()
        self.app.processEvents()
        self.list_widget = self.window.list_widget

    def close_window(self) -> None:
        self.window._quitting_app = True
        self.window.tray_icon.hide()
        self.window.close()
        self.app.processEvents()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def visible_ids(self) -> set[int]:
        viewport = self.list_widget.viewport().rect()
        return {
            todo_id for todo_id, item in self.window._todo_items_by_id.items()
            if self.list_widget.visualItemRect(item).intersects(viewport)
        }

    def test_tick_refreshes_only_visible_and_partially_visible_cards(self) -> None:
        self.list_widget.verticalScrollBar().setValue(45)
        visible = self.visible_ids()
        self.assertLess(len(visible), 100)
        self.assertGreater(len(visible), 0)
        self.now += timedelta(minutes=30)
        with ExitStack() as spies:
            updates = {
                todo_id: spies.enter_context(patch.object(card, "update_timer_display", wraps=card.update_timer_display))
                for todo_id, card in self.window._todo_widgets_by_id.items()
            }
            layout = spies.enter_context(patch.object(self.list_widget, "doItemsLayout"))
            self.window.tick_update()
            self.assertEqual({key for key, spy in updates.items() if spy.called}, visible)
            layout.assert_not_called()
        self.save.assert_not_called()

    def test_scrolling_into_view_refreshes_stale_text_before_next_tick(self) -> None:
        card = self.window._todo_widgets_by_id[99]
        self.assertNotIn(99, self.visible_ids())
        self.now += timedelta(minutes=30)
        self.list_widget.verticalScrollBar().setValue(self.list_widget.verticalScrollBar().maximum())
        self.assertIn(99, self.visible_ids())
        self.assertEqual(card.timer_display_label.full_text, "剩余: 1时 30分")
        self.save.assert_not_called()

    def test_resize_exposes_current_timer_without_waiting_for_tick(self) -> None:
        first_hidden_id = min(set(range(100)) - self.visible_ids())
        card = self.window._todo_widgets_by_id[first_hidden_id]
        self.now += timedelta(minutes=30)
        self.window.resize(440, 1000)
        self.app.processEvents()
        self.assertIn(first_hidden_id, self.visible_ids())
        self.assertEqual(card.timer_display_label.full_text, "剩余: 1时 30分")

    def test_filter_reuses_card_and_refreshes_its_stale_timer(self) -> None:
        card = self.window._todo_widgets_by_id[99]
        self.now += timedelta(minutes=30)
        self.window.filter_combo.setCurrentText("高优先级")
        self.app.processEvents()
        self.assertIs(self.window._todo_widgets_by_id[99], card)
        self.assertEqual(card.timer_display_label.full_text, "剩余: 1时 30分")

    def test_hidden_window_skips_timer_work_and_restore_refreshes_immediately(self) -> None:
        self.window.hide()
        self.now += timedelta(minutes=30)
        with ExitStack() as spies:
            updates = [
                spies.enter_context(patch.object(card, "update_timer_display", wraps=card.update_timer_display))
                for card in self.window._todo_widgets_by_id.values()
            ]
            self.window.tick_update()
            self.assertFalse(any(spy.called for spy in updates))
        self.window.show()
        self.app.processEvents()
        for todo_id in self.visible_ids():
            self.assertEqual(
                self.window._todo_widgets_by_id[todo_id].timer_display_label.full_text,
                "剩余: 1时 30分",
            )

    def test_filter_and_hidden_window_never_skip_due_notification_scan(self) -> None:
        self.window.filter_combo.setCurrentText("已完成")
        self.window.hide()
        self.now += timedelta(hours=3)
        with patch.object(self.window, "_show_notification_batch") as notify:
            self.window.tick_update()
        requests = notify.call_args.args[0]
        self.assertEqual({todo["id"] for todo, is_due in requests if is_due}, set(range(100)))
        self.assertTrue(all(todo["notifiedForDue"] for todo in self.tasks))
        self.save.assert_called_once_with(self.tasks)

    def test_minimized_window_defers_timer_refresh_until_restored(self) -> None:
        self.window.tray_icon.hide()
        self.window.showMinimized()
        self.app.processEvents()
        self.assertTrue(self.window.windowState() & Qt.WindowState.WindowMinimized)
        self.now += timedelta(minutes=30)
        card = self.window._todo_widgets_by_id[0]
        with patch.object(card, "update_timer_display", wraps=card.update_timer_display) as update:
            self.window.tick_update()
            update.assert_not_called()
        self.window.showNormal()
        self.app.processEvents()
        self.assertEqual(card.timer_display_label.full_text, "剩余: 1时 30分")


if __name__ == "__main__":
    unittest.main()
