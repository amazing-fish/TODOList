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
            self.assertIsNone(window.todos[0]["recurrence"])
            window.todos[0]["priority"] = "高"
            window.undo_toast_bar.trigger_undo()
            self.assertFalse(window.todos[0]["completed"])
            self.assertEqual(window.todos[0]["recurrence"]["frequency"], "daily")
            self.assertEqual(window.todos[0]["priority"], "高")

    def test_coderabbit_recurrence_edge_cases(self) -> None:
        # 1. 非有限数 Infinity / NaN 不引发 OverflowError 且安全回退
        inf_rule = normalize_recurrence({"frequency": "daily", "interval": float("inf")})
        self.assertEqual(inf_rule, {"frequency": "daily", "interval": 1, "skipWeekends": False})
        inf_weekly = normalize_recurrence({"frequency": "weekly", "weekdays": [float("inf"), 2]})
        self.assertEqual(inf_weekly, {"frequency": "weekly", "weekdays": [2]})

        # 2. 多年前的工作日任务顺延强制快进到晚于 reference_utc 的未来日期
        old_due = datetime(2020, 1, 1, 9, 0, tzinfo=timezone.utc)
        now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
        caught_up = calculate_next_due_utc(
            old_due.isoformat(),
            {"frequency": "weekdays"},
            reference_utc=now,
            target_tz=timezone.utc,
        )
        self.assertGreater(datetime.fromisoformat(caught_up), now)

        # 3. 9999-12-31 无法表示下一日抛出 OverflowError/ValueError，UI 完成路径安全回滚
        with self.assertRaises((OverflowError, ValueError)):
            calculate_next_due_utc(
                "9999-12-31T09:00:00+00:00",
                {"frequency": "daily", "interval": 1},
                reference_utc=datetime(9999, 12, 31, 8, 0, tzinfo=timezone.utc),
                target_tz=timezone.utc,
            )

        # 4. 月末 31 日规则在 2 月 28 日卡片上仅修改文案时，不退化为 28 日
        feb28_task = {
            "id": 91,
            "text": "月末对账",
            "priority": "中",
            "dueDate": "2026-02-28T09:00:00+00:00",
            "reminderOffset": 0,
            "recurrence": {"frequency": "monthly", "day": 31},
            "completed": False,
            "createdAt": "2026-01-31T09:00:00+00:00",
        }
        dlg = TaskEditDialog(todo_item=feb28_task)
        self.addCleanup(dlg.deleteLater)
        dlg.task_input.setPlainText("月末对账（已改文案）")
        self.assertEqual(dlg.get_task_data()["recurrence"], {"frequency": "monthly", "day": 31})

        # 5. 无截止时间时右键菜单显示“标记为已完成”而不是“完成本周期”
        from PySide6.QtGui import QContextMenuEvent
        from PySide6.QtWidgets import QMenu

        no_due_task = dict(feb28_task, dueDate=None)
        card = TodoItemWidget(no_due_task)
        self.addCleanup(card.deleteLater)
        labels: list[str] = []

        class _FakeMenu(QMenu):
            def exec(self, *args, **kwargs):
                labels.extend(a.text() for a in self.actions() if a.text())
                return None

        with patch("todo_app.widgets.QMenu", _FakeMenu):
            card.contextMenuEvent(
                QContextMenuEvent(QContextMenuEvent.Reason.Mouse, card.rect().center(), card.rect().center())
            )
        self.assertIn("标记为已完成", labels)
        self.assertNotIn("完成本周期（顺延下次）", labels)

    def test_notification_complete_and_schedule_edit_undo_guard(self) -> None:
        from datetime import timedelta

        due = "2030-05-01T09:00:00+00:00"
        todo = {
            "id": 88,
            "text": "晨会提醒",
            "priority": "中",
            "dueDate": due,
            "reminderOffset": 0,
            "recurrence": {"frequency": "daily", "interval": 1, "skipWeekends": False},
            "completed": False,
            "createdAt": "2030-04-30T09:00:00+00:00",
            "snoozeUntil": None,
            "notifiedForReminder": True,
            "notifiedForDue": True,
            "lastNotifiedAt": due,
        }
        window = self._create_window([todo])
        with patch("todo_app.main_window.save_todos", return_value=True):
            # 1. 从提醒点击完成周期任务，触发 5 秒撤销且可恢复原 dueDate
            window._handle_notification_complete([88])
            self.assertFalse(window.todos[0]["completed"])
            advanced_due = window.todos[0]["dueDate"]
            self.assertNotEqual(advanced_due, due)
            self.assertTrue(window.undo_toast_bar.has_active_undo())
            window.undo_toast_bar.trigger_undo()
            self.assertEqual(window.todos[0]["dueDate"], due)

            # 2. 完成顺延后再通过推迟改变调度时间，旧撤销不得覆盖新时间
            window.toggle_complete_todo(88)
            self.assertTrue(window.undo_toast_bar.has_active_undo())
            window._handle_notification_snooze([88], timedelta(hours=3))
            snoozed_due = window.todos[0]["dueDate"]
            window.undo_toast_bar.trigger_undo()
            self.assertEqual(window.todos[0]["dueDate"], snoozed_due)

            # 3. 通知完成在持久化失败时全部回滚，既不清除通知也不触发 Undo
            window.undo_toast_bar.dismiss()
            with (
                patch.object(window, "_persist_todos", return_value=False),
                patch.object(window, "_remove_notification_tasks") as rm_mock,
                patch("todo_app.main_window.QMessageBox.warning") as warn_mock,
            ):
                window._handle_notification_complete([88])
                self.assertEqual(window.todos[0]["dueDate"], snoozed_due)
                rm_mock.assert_not_called()
                self.assertFalse(window.undo_toast_bar.has_active_undo())
                warn_mock.assert_called_once()

    def test_dst_gap_preserves_original_wall_clock_anchor(self) -> None:
        from datetime import date as _date, timedelta

        class _SpringGapDatetime(datetime):
            def astimezone(self, tz=None):
                if tz is not None:
                    return super().astimezone(tz)
                if self.tzinfo is not None:
                    # UTC -> UTC-5（3 月 7 日 07:30 UTC 为 02:30-05:00）
                    return (self - timedelta(hours=5)).replace(tzinfo=timezone(timedelta(hours=-5)))
                # 无时区墙钟：3 月 8 日 02:30 不存在时回退解析为 03:30-04:00；3 月 9 日还原 02:30-04:00
                if self.date() == _date(2026, 3, 8) and self.hour == 2 and self.minute == 30:
                    return datetime(2026, 3, 8, 3, 30, tzinfo=timezone(timedelta(hours=-4)))
                offset = -5 if self.date() <= _date(2026, 3, 7) else -4
                return datetime(
                    self.year,
                    self.month,
                    self.day,
                    self.hour,
                    self.minute,
                    self.second,
                    self.microsecond,
                    tzinfo=timezone(timedelta(hours=offset)),
                )

        # 原规则为每日 02:30，跨越 3 月 8 日跳变缺口后在 3 月 9 日仍应维持 02:30-04:00（06:30 UTC）
        with patch("todo_app.scheduling.datetime", _SpringGapDatetime):
            next_iso = calculate_next_due_utc(
                "2026-03-07T07:30:00+00:00",
                {"frequency": "daily", "interval": 1, "skipWeekends": False},
                reference_utc=_SpringGapDatetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc),
                target_tz=None,
            )
        self.assertEqual(next_iso, "2026-03-09T06:30:00+00:00")

        # 连续两次跨 DST 缺口完成：首次完成把 March 8 存为 03:30 (-04) 并固化 anchorTime="02:30"，
        # 次日再完成时仍基于 anchorTime 还原到 March 9 02:30 (-04, 即 06:30 UTC)
        gap_todo = {
            "id": 92,
            "text": "跨DST任务",
            "dueDate": "2026-03-07T07:30:00+00:00",
            "recurrence": {"frequency": "daily", "interval": 1, "skipWeekends": False},
        }
        with patch("todo_app.scheduling.datetime", _SpringGapDatetime):
            step1 = build_recurrence_completion_fields(
                gap_todo,
                now_utc=_SpringGapDatetime(2026, 3, 7, 7, 30, tzinfo=timezone.utc),
                target_tz=None,
            )
            self.assertEqual(step1["dueDate"], "2026-03-08T07:30:00+00:00")
            self.assertEqual(step1["recurrence"].get("anchorTime"), "02:30")

            saved_gap_todo = dict(gap_todo, **step1)
            step2 = build_recurrence_completion_fields(
                saved_gap_todo,
                now_utc=_SpringGapDatetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc),
                target_tz=None,
            )
        self.assertEqual(step2["dueDate"], "2026-03-09T06:30:00+00:00")

    def test_daily_skip_weekends_interval_gt_one_catches_up_decades(self) -> None:
        old_monday = datetime(2000, 1, 3, 9, 0, tzinfo=timezone.utc)
        now_2030 = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
        caught_up = calculate_next_due_utc(
            old_monday.isoformat(),
            {"frequency": "daily", "interval": 2, "skipWeekends": True},
            reference_utc=now_2030,
            target_tz=timezone.utc,
        )
        caught_dt = datetime.fromisoformat(caught_up)
        self.assertGreater(caught_dt, now_2030)
        self.assertLess(caught_dt.weekday(), 5)
        self.assertEqual(caught_up, "2030-01-02T09:00:00+00:00")

    def test_edit_dialog_preserves_implicit_empty_weekly_and_updates_anchor_time(self) -> None:
        from PySide6.QtCore import QTime

        todo = {
            "id": 93,
            "text": "隐式每周任务",
            "priority": "中",
            "dueDate": "2026-04-24T10:00:00+00:00",
            "reminderOffset": 0,
            "recurrence": {"frequency": "weekly", "weekdays": [], "anchorTime": "02:30"},
            "completed": False,
            "createdAt": "2026-04-20T08:00:00+00:00",
        }
        dlg = TaskEditDialog(todo_item=todo)
        self.addCleanup(dlg.deleteLater)
        dlg.task_input.setPlainText("隐式每周任务（改标题）")
        data = dlg.get_task_data()
        self.assertEqual(data["recurrence"], {"frequency": "weekly", "weekdays": [], "anchorTime": "02:30"})

        dlg.time_edit.setTime(QTime(4, 15))
        edited_data = dlg.get_task_data()
        self.assertEqual(edited_data["recurrence"]["anchorTime"], "04:15")

    def test_persist_failure_rollback_across_notification_card_and_retryable_undo(self) -> None:
        due = "2030-05-01T09:00:00+00:00"
        todo = {
            "id": 94,
            "text": "持久化回滚闭环",
            "priority": "中",
            "dueDate": due,
            "reminderOffset": 0,
            "recurrence": {"frequency": "daily", "interval": 1, "skipWeekends": False},
            "completed": False,
            "createdAt": "2030-04-30T09:00:00+00:00",
            "snoozeUntil": None,
            "notifiedForReminder": True,
            "notifiedForDue": True,
            "lastNotifiedAt": due,
        }
        window = self._create_window([todo])

        # 1. 通知弹窗完成但持久化失败 -> 敞开的通知行应立即还原为原截止时间
        with (
            patch("todo_app.main_window.play_sound_effect"),
            patch.object(window, "_persist_todos", return_value=False),
            patch("todo_app.main_window.QMessageBox.warning") as warn_mock,
        ):
            window._show_notification_batch([(window.todos[0], True)])
            before_detail = window._notification_dialog._task_rows[94]["detail_label"].text()
            window._handle_notification_complete([94])
            after_detail = window._notification_dialog._task_rows[94]["detail_label"].text()
            self.assertEqual(window.todos[0]["dueDate"], due)
            self.assertEqual(after_detail, before_detail)
            warn_mock.assert_called_once()

        # 2. 卡片 toggle_complete / finish_recurrence 持久化失败 -> 回滚状态、保留提醒、不弹 Toast
        with (
            patch.object(window, "_persist_todos", return_value=False),
            patch("todo_app.main_window.QMessageBox.warning") as warn_mock,
        ):
            window.toggle_complete_todo(94)
            self.assertEqual(window.todos[0]["dueDate"], due)
            self.assertIn(94, window._notification_dialog._task_rows)
            self.assertFalse(window.undo_toast_bar.has_active_undo())

            window.handle_finish_recurrence_request(94)
            self.assertFalse(window.todos[0]["completed"])
            self.assertIsNotNone(window.todos[0]["recurrence"])
            self.assertIn(94, window._notification_dialog._task_rows)
            self.assertFalse(window.undo_toast_bar.has_active_undo())
            self.assertEqual(warn_mock.call_count, 2)

        # 3. Undo 期间持久化失败 -> 回滚撤销并保持 Undo Toast 可重试，恢复后再次点击撤销成功
        with patch.object(window, "_persist_todos", return_value=True):
            window.toggle_complete_todo(94)
            advanced_due = window.todos[0]["dueDate"]
            self.assertNotEqual(advanced_due, due)
            self.assertTrue(window.undo_toast_bar.has_active_undo())

        with (
            patch.object(window, "_persist_todos", return_value=False),
            patch("todo_app.main_window.QMessageBox.warning") as warn_mock,
        ):
            self.assertFalse(window.undo_toast_bar.trigger_undo())
            self.assertEqual(window.todos[0]["dueDate"], advanced_due)
            self.assertTrue(window.undo_toast_bar.has_active_undo())
            warn_mock.assert_called_once()

        with patch.object(window, "_persist_todos", return_value=True):
            self.assertTrue(window.undo_toast_bar.trigger_undo())
            self.assertEqual(window.todos[0]["dueDate"], due)
            self.assertFalse(window.undo_toast_bar.has_active_undo())


if __name__ == "__main__":
    unittest.main()
