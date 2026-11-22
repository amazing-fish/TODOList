import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from todo_app.dialogs import TaskEditDialog
from todo_app.main_window import ModernTodoAppWindow
from todo_app.scheduling import (
    build_recurrence_completion_fields,
    calculate_next_due_utc,
    format_recurrence_label,
    normalize_recurrence,
)
from todo_app.storage import normalize_todo_list
from todo_app.widgets import TodoItemWidget


class RecurrenceLogicTests(unittest.TestCase):
    def test_normalize_and_format_recurrence(self) -> None:
        self.assertIsNone(normalize_recurrence(None))
        self.assertIsNone(normalize_recurrence({"frequency": "none"}))
        self.assertIsNone(normalize_recurrence({"frequency": "invalid"}))

        daily = normalize_recurrence({"frequency": "daily", "interval": 2, "skipWeekends": True})
        self.assertEqual(
            daily,
            {"frequency": "daily", "interval": 2, "skipWeekends": True},
        )
        self.assertEqual(format_recurrence_label(daily), "每2天(工作日)")

        weekly = normalize_recurrence({"frequency": "weekly", "weekdays": [4, 0, 4, 9]})
        self.assertEqual(
            weekly,
            {"frequency": "weekly", "weekdays": [0, 4]},
        )
        self.assertEqual(format_recurrence_label(weekly), "每周一/周五")

        monthly = normalize_recurrence({"frequency": "monthly", "day": 31})
        self.assertEqual(monthly, {"frequency": "monthly", "day": 31})
        self.assertEqual(format_recurrence_label(monthly), "每月31日")

    def test_calculate_next_due_utc_handles_skip_weekends_weekly_and_month_end(self) -> None:
        friday = datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc)
        next_weekday = calculate_next_due_utc(
            friday.isoformat(),
            {"frequency": "daily", "skipWeekends": True},
            reference_utc=friday,
            target_tz=timezone.utc,
        )
        self.assertEqual(next_weekday, "2026-04-20T09:00:00+00:00")

        tuesday = datetime(2026, 4, 14, 10, 30, tzinfo=timezone.utc)
        next_weekly = calculate_next_due_utc(
            tuesday.isoformat(),
            {"frequency": "weekly", "weekdays": [0, 3]},
            reference_utc=tuesday,
            target_tz=timezone.utc,
        )
        self.assertEqual(next_weekly, "2026-04-16T10:30:00+00:00")

        jan_31 = datetime(2026, 1, 31, 8, 15, tzinfo=timezone.utc)
        next_feb = calculate_next_due_utc(
            jan_31.isoformat(),
            {"frequency": "monthly", "day": 31},
            reference_utc=jan_31,
            target_tz=timezone.utc,
        )
        self.assertEqual(next_feb, "2026-02-28T08:15:00+00:00")

    def test_calculate_next_due_catches_up_past_now(self) -> None:
        old_due = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        now = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
        next_due = calculate_next_due_utc(
            old_due.isoformat(),
            {"frequency": "daily", "interval": 1},
            reference_utc=now,
            target_tz=timezone.utc,
        )
        self.assertEqual(next_due, "2026-01-06T09:00:00+00:00")

    def test_build_recurrence_completion_fields_and_storage_migration(self) -> None:
        due = datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)
        todo = {
            "id": 1,
            "text": "每日站会",
            "dueDate": due.isoformat(),
            "recurrence": {"frequency": "daily", "interval": 1},
            "snoozeUntil": "2026-04-10T09:10:00+00:00",
            "notifiedForReminder": True,
            "notifiedForDue": True,
        }
        fields = build_recurrence_completion_fields(todo, now_utc=due, target_tz=timezone.utc)
        self.assertIsNotNone(fields)
        self.assertFalse(fields["completed"])
        self.assertIsNone(fields["snoozeUntil"])
        self.assertFalse(fields["notifiedForReminder"])
        self.assertFalse(fields["notifiedForDue"])
        self.assertEqual(fields["dueDate"], "2026-04-11T09:00:00+00:00")

        normalized = normalize_todo_list(
            [
                {"id": 1, "text": "a", "recurrence": {"frequency": "weekly", "weekdays": [2]}},
                {"id": 2, "text": "b", "recurrence": {"frequency": "bogus"}},
                {"id": 3, "text": "legacy"},
            ]
        )
        self.assertEqual(normalized[0]["recurrence"]["weekdays"], [2])
        self.assertIsNone(normalized[1]["recurrence"])
        self.assertNotIn("recurrence", normalized[2])


class RecurrenceGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _close_window(window: ModernTodoAppWindow) -> None:
        window.master_timer.stop()
        window._quitting_app = True
        window.tray_icon.hide()
        window.close()

    def _create_window(self, todos: list[dict]) -> ModernTodoAppWindow:
        settings = MagicMock()
        settings.value.return_value = None
        with (
            patch("todo_app.main_window.load_todos", return_value=todos),
            patch("todo_app.main_window.save_todos", return_value=True),
            patch("todo_app.main_window.QSettings", return_value=settings),
        ):
            window = ModernTodoAppWindow()
        window.master_timer.stop()
        window.show()
        self.app.processEvents()
        self.addCleanup(self._close_window, window)
        return window

    def test_dialog_round_trip_and_widget_badge(self) -> None:
        todo = {
            "id": 10,
            "text": "周报提交",
            "priority": "高",
            "dueDate": "2026-04-24T10:00:00+00:00",
            "reminderOffset": 900,
            "recurrence": {"frequency": "weekly", "weekdays": [4]},
            "completed": False,
            "createdAt": "2026-04-20T08:00:00+00:00",
        }
        dialog = TaskEditDialog(todo_item=todo)
        self.addCleanup(dialog.deleteLater)
        data = dialog.get_task_data()
        self.assertEqual(data["recurrence"]["frequency"], "weekly")
        self.assertEqual(data["recurrence"]["weekdays"], [4])

        widget = TodoItemWidget(todo)
        self.addCleanup(widget.deleteLater)
        self.assertFalse(widget.recurrence_badge_label.isHidden())
        self.assertIn("每周五", widget.recurrence_badge_label.text())

    def test_completing_recurring_task_advances_and_supports_undo_and_finish(self) -> None:
        due = "2030-05-01T09:00:00+00:00"
        todo = {
            "id": 77,
            "text": "每日复盘",
            "priority": "中",
            "dueDate": due,
            "reminderOffset": -1,
            "recurrence": {"frequency": "daily", "interval": 1, "skipWeekends": False},
            "completed": False,
            "createdAt": "2030-04-30T09:00:00+00:00",
            "snoozeUntil": None,
            "notifiedForReminder": False,
            "notifiedForDue": False,
            "lastNotifiedAt": None,
        }
        window = self._create_window([todo])
        with patch("todo_app.main_window.save_todos", return_value=True):
            window.toggle_complete_todo(77)
            self.assertFalse(window.todos[0]["completed"])
            self.assertNotEqual(window.todos[0]["dueDate"], due)
            self.assertTrue(window.undo_toast_bar.has_active_undo())

            # 模拟顺延后改了文案，撤销应保留新文案只回滚完成与截止推进状态
            window.todos[0]["text"] = "每日复盘（已修订）"
            window.undo_toast_bar.trigger_undo()
            self.assertEqual(window.todos[0]["dueDate"], due)
            self.assertFalse(window.todos[0]["completed"])
            self.assertEqual(window.todos[0]["text"], "每日复盘（已修订）")

            window.handle_finish_recurrence_request(77)
            self.assertTrue(window.todos[0]["completed"])
            window.todos[0]["priority"] = "高"
            window.undo_toast_bar.trigger_undo()
            self.assertFalse(window.todos[0]["completed"])
            self.assertEqual(window.todos[0]["priority"], "高")


if __name__ == "__main__":
    unittest.main()
