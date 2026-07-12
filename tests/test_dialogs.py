"""任务编辑对话框的时间往返测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QDateTime, QTime, QTimeZone  # noqa: E402
from PySide6.QtWidgets import QApplication, QDateEdit, QTimeEdit  # noqa: E402

from todo_app.dialogs import TaskEditDialog, _default_due_datetime  # noqa: E402
from todo_app.scheduling import build_edit_update_fields  # noqa: E402


class TaskEditDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_default_due_datetime_is_exactly_one_visible_hour_later(self) -> None:
        cases = [
            (
                QDateTime(QDate(2026, 7, 12), QTime(13, 42, 37, 500)),
                QDateTime(QDate(2026, 7, 12), QTime(14, 42)),
            ),
            (
                QDateTime(QDate(2026, 7, 12), QTime(23, 30)),
                QDateTime(QDate(2026, 7, 13), QTime(0, 30)),
            ),
            (
                QDateTime(QDate(2026, 7, 12), QTime(5, 30)),
                QDateTime(QDate(2026, 7, 12), QTime(6, 30)),
            ),
        ]

        for now, expected in cases:
            with self.subTest(now=now.toString("yyyy-MM-ddTHH:mm:ss.zzz")):
                self.assertEqual(_default_due_datetime(now), expected)

    def test_default_due_datetime_preserves_repeated_hour_instance(self) -> None:
        zone = QTimeZone(b"America/New_York")
        now_ms = int(
            datetime(2026, 11, 1, 5, 30, 45, 500000, tzinfo=timezone.utc).timestamp()
            * 1000
        )
        expected_ms = int(
            datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).timestamp() * 1000
        )
        now = QDateTime.fromMSecsSinceEpoch(now_ms, zone)

        actual = _default_due_datetime(now)

        self.assertEqual(actual.toMSecsSinceEpoch(), expected_ms)
        self.assertGreater(actual.toMSecsSinceEpoch(), now.toMSecsSinceEpoch())

    def test_new_dialog_uses_and_preserves_the_same_default_target(self) -> None:
        zone = QTimeZone(b"America/New_York")
        target_ms = int(
            datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).timestamp() * 1000
        )
        target = QDateTime.fromMSecsSinceEpoch(target_ms, zone)

        with patch("todo_app.dialogs._default_due_datetime", return_value=target) as calculate:
            dialog = TaskEditDialog()
        self.addCleanup(dialog.close)

        calculate.assert_called_once()
        self.assertEqual(dialog.date_edit.date(), target.date())
        self.assertEqual(dialog.time_edit.time(), target.time())

        dialog.task_input.setPlainText("重复小时任务")
        dialog.set_due_date_button.setChecked(True)
        saved_due = datetime.fromisoformat(dialog.get_task_data()["dueDate"])
        self.assertEqual(saved_due.astimezone(timezone.utc), datetime.fromtimestamp(target_ms / 1000, timezone.utc))

    def test_offset_due_date_round_trip_preserves_snooze_state(self) -> None:
        existing = {
            "text": "延后后的任务",
            "priority": "中",
            "dueDate": "2026-07-12T03:28:39.634786+08:00",
            "reminderOffset": 0,
            "completed": False,
            "snoozeUntil": "2026-07-12T03:28:39.634786+08:00",
            "notifiedForReminder": True,
            "notifiedForDue": True,
            "lastNotifiedAt": "2026-07-12T03:13:00.763984+08:00",
        }
        dialog = TaskEditDialog(todo_item=existing)

        edited = dialog.get_task_data()
        updated = build_edit_update_fields(existing, edited)

        self.assertEqual(edited["dueDate"], existing["dueDate"])
        original_instant = datetime.fromisoformat(existing["dueDate"]).astimezone(timezone.utc)
        edited_instant = datetime.fromisoformat(edited["dueDate"]).astimezone(timezone.utc)
        self.assertLess(abs((edited_instant - original_instant).total_seconds()), 0.001)
        self.assertEqual(updated["dueDate"], existing["dueDate"])
        self.assertNotIn("snoozeUntil", updated)
        self.assertNotIn("notifiedForReminder", updated)
        self.assertNotIn("notifiedForDue", updated)
        self.assertNotIn("lastNotifiedAt", updated)
        dialog.close()

    def test_editing_visible_minute_clears_hidden_seconds(self) -> None:
        existing = {
            "text": "延后后的任务",
            "priority": "中",
            "dueDate": "2026-07-12T03:28:39.634000+08:00",
            "reminderOffset": 0,
        }
        dialog = TaskEditDialog(todo_item=existing)
        self.addCleanup(dialog.close)

        dialog.time_edit.setTime(dialog.time_edit.time().addSecs(60))

        edited_due = datetime.fromisoformat(dialog.get_task_data()["dueDate"])
        self.assertEqual(edited_due.second, 0)
        self.assertEqual(edited_due.microsecond, 0)

    def test_due_controls_keep_wheel_time_and_inline_calendar(self) -> None:
        dialog = TaskEditDialog()
        self.addCleanup(dialog.close)

        self.assertIsInstance(dialog.time_edit, QTimeEdit)
        self.assertEqual(dialog.time_edit.displayFormat(), "HH:mm")
        self.assertIsInstance(dialog.date_edit, QDateEdit)
        self.assertEqual(dialog.date_edit.displayFormat(), "yyyy-MM-dd")
        self.assertTrue(dialog.date_edit.calendarPopup())

    def test_due_controls_combine_date_and_time_or_clear_due_date(self) -> None:
        dialog = TaskEditDialog()
        self.addCleanup(dialog.close)
        dialog.task_input.setPlainText("跨日期任务")
        dialog.set_due_date_button.setChecked(True)
        dialog.date_edit.setDate(QDate(2026, 7, 13))
        dialog.time_edit.setTime(QTime(9, 30))

        data = dialog.get_task_data()

        expected = QDateTime(QDate(2026, 7, 13), QTime(9, 30)).toUTC().toPython()
        if expected.tzinfo is None:
            expected = expected.replace(tzinfo=timezone.utc)
        self.assertEqual(data["dueDate"], expected.isoformat())

        dialog.set_due_date_button.setChecked(False)
        self.assertIsNone(dialog.get_task_data()["dueDate"])


if __name__ == "__main__":
    unittest.main()
