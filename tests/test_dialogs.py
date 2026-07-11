"""任务编辑对话框的时间往返测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from todo_app.dialogs import TaskEditDialog  # noqa: E402
from todo_app.scheduling import build_edit_update_fields  # noqa: E402


class TaskEditDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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

        original_instant = datetime.fromisoformat(existing["dueDate"]).astimezone(timezone.utc)
        edited_instant = datetime.fromisoformat(edited["dueDate"]).astimezone(timezone.utc)
        self.assertLess(abs((edited_instant - original_instant).total_seconds()), 0.001)
        self.assertEqual(updated["dueDate"], existing["dueDate"])
        self.assertNotIn("snoozeUntil", updated)
        self.assertNotIn("notifiedForReminder", updated)
        self.assertNotIn("notifiedForDue", updated)
        self.assertNotIn("lastNotifiedAt", updated)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
