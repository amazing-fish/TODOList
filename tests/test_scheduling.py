"""提醒与编辑调度规则测试。"""
from __future__ import annotations

import unittest
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCHEDULING_PATH = Path(__file__).resolve().parents[1] / "todo_app" / "scheduling.py"
SPEC = importlib.util.spec_from_file_location("todo_app_scheduling", SCHEDULING_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("无法加载调度规则模块。")
scheduling = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scheduling)

build_edit_update_fields = scheduling.build_edit_update_fields
build_snooze_update_fields = scheduling.build_snooze_update_fields


class SchedulingRulesTest(unittest.TestCase):
    def test_snooze_due_task_moves_due_date_to_snooze_target(self) -> None:
        now = datetime(2026, 5, 10, 12, 30, tzinfo=timezone.utc)
        todo = {
            "dueDate": datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc).isoformat(),
            "lastNotifiedAt": now.isoformat(),
            "notifiedForReminder": True,
            "notifiedForDue": True,
        }

        updated = build_snooze_update_fields(todo, timedelta(minutes=15), now)

        self.assertEqual(
            updated["dueDate"],
            datetime(2026, 5, 10, 12, 45, tzinfo=timezone.utc).isoformat(),
        )
        self.assertEqual(
            updated["snoozeUntil"],
            datetime(2026, 5, 10, 12, 45, tzinfo=timezone.utc).isoformat(),
        )
        self.assertIsNone(updated["lastNotifiedAt"])
        self.assertFalse(updated["notifiedForReminder"])
        self.assertFalse(updated["notifiedForDue"])

    def test_snooze_future_task_extends_due_date_by_duration(self) -> None:
        now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
        todo = {
            "dueDate": datetime(2026, 5, 10, 13, 0, tzinfo=timezone.utc).isoformat(),
        }

        updated = build_snooze_update_fields(todo, timedelta(minutes=15), now)

        self.assertEqual(
            updated["dueDate"],
            datetime(2026, 5, 10, 13, 15, tzinfo=timezone.utc).isoformat(),
        )

    def test_text_only_edit_preserves_existing_snooze_state(self) -> None:
        existing = {
            "text": "旧任务",
            "priority": "中",
            "dueDate": "2026-05-10T13:15:00+00:00",
            "reminderOffset": 900,
            "snoozeUntil": "2026-05-10T12:45:00+00:00",
            "notifiedForReminder": False,
            "notifiedForDue": False,
            "lastNotifiedAt": None,
        }
        edited = {
            "text": "新任务",
            "priority": "高",
            "dueDate": "2026-05-10T13:15:00+00:00",
            "reminderOffset": 900,
        }

        updated = build_edit_update_fields(existing, edited)

        self.assertEqual(updated["text"], "新任务")
        self.assertEqual(updated["priority"], "高")
        self.assertNotIn("snoozeUntil", updated)
        self.assertNotIn("lastNotifiedAt", updated)

    def test_schedule_edit_resets_snooze_and_notification_state(self) -> None:
        existing = {
            "text": "任务",
            "priority": "中",
            "dueDate": "2026-05-10T13:15:00+00:00",
            "reminderOffset": 900,
            "snoozeUntil": "2026-05-10T12:45:00+00:00",
            "notifiedForReminder": True,
            "notifiedForDue": True,
            "lastNotifiedAt": "2026-05-10T12:30:00+00:00",
        }
        edited = {
            "text": "任务",
            "priority": "中",
            "dueDate": "2026-05-10T14:00:00+00:00",
            "reminderOffset": 900,
        }

        updated = build_edit_update_fields(existing, edited)

        self.assertIsNone(updated["snoozeUntil"])
        self.assertFalse(updated["notifiedForReminder"])
        self.assertFalse(updated["notifiedForDue"])
        self.assertIsNone(updated["lastNotifiedAt"])


if __name__ == "__main__":
    unittest.main()
