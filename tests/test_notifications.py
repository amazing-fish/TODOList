"""软件内汇总提醒窗口与批次协调测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QDialog,
    QLabel,
    QPushButton,
    QToolButton,
)

from todo_app.dialogs import NotificationDialog  # noqa: E402
from todo_app.main_window import ModernTodoAppWindow  # noqa: E402


def make_todo(todo_id: int, text: str) -> dict:
    return {
        "id": todo_id,
        "text": text,
        "priority": "中",
        "dueDate": "2026-07-12T06:00:00+00:00",
        "reminderOffset": 0,
        "completed": False,
        "createdAt": "2026-07-12T05:00:00+00:00",
        "snoozeUntil": None,
        "notifiedForReminder": False,
        "notifiedForDue": False,
        "lastNotifiedAt": None,
    }


class NotificationDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_tasks_are_aggregated_deduplicated_and_upgraded(self) -> None:
        first = make_todo(1, "第一项")
        second = make_todo(2, "第二项")
        dialog = NotificationDialog([(first, False), (second, True)])
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.task_ids(), [1, 2])
        self.assertEqual(dialog.title_label.text(), "2 个任务需要处理")

        dialog.add_or_update_tasks([(first, True)])

        self.assertEqual(dialog.task_ids(), [1, 2])
        status_label = dialog.findChild(QLabel, "notificationStatus_1")
        self.assertIsNotNone(status_label)
        self.assertEqual(status_label.text(), "已到期")

    def test_dialog_has_only_inline_actions_and_keeps_remaining_rows(self) -> None:
        dialog = NotificationDialog(
            [(make_todo(1, "第一项"), True), (make_todo(2, "第二项"), True)]
        )
        destroyed = []
        dialog.destroyed.connect(lambda: destroyed.append(True))
        self.assertEqual(dialog.layout().count(), 2)
        self.assertEqual(dialog.findChildren(QCheckBox), [])
        self.assertFalse(hasattr(dialog, "complete_button"))
        self.assertFalse(hasattr(dialog, "snooze_default_button"))
        self.assertFalse(hasattr(dialog, "snooze_menu_button"))
        self.assertFalse(hasattr(dialog, "ignore_button"))
        self.assertIsNone(dialog.findChild(QPushButton, "batchIgnoreButton"))

        dialog.show()
        self.app.processEvents()
        dialog.remove_tasks([1])
        self.assertEqual(dialog.task_ids(), [2])
        self.assertTrue(dialog.isVisible())
        dialog.remove_tasks([2])
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(destroyed, [True])

    def test_inline_actions_target_only_their_own_task(self) -> None:
        dialog = NotificationDialog(
            [(make_todo(1, "第一项"), True), (make_todo(2, "第二项"), True)]
        )
        self.addCleanup(dialog.close)
        completed: list[list[int]] = []
        snoozed: list[tuple[list[int], timedelta]] = []
        ignored: list[list[int]] = []
        dialog.complete_requested.connect(completed.append)
        dialog.snooze_requested.connect(lambda ids, duration: snoozed.append((ids, duration)))
        dialog.ignore_requested.connect(ignored.append)

        complete_first = dialog.findChild(QPushButton, "notificationComplete_1")
        snooze_second = dialog.findChild(QToolButton, "notificationSnooze_2")
        ignore_first = dialog.findChild(QPushButton, "notificationIgnore_1")
        self.assertIsNotNone(complete_first)
        self.assertIsNotNone(snooze_second)
        self.assertIsNotNone(ignore_first)
        self.assertEqual(snooze_second.text(), "推迟 1 小时")
        self.assertEqual(
            snooze_second.popupMode(),
            QToolButton.ToolButtonPopupMode.MenuButtonPopup,
        )
        self.assertIn("点击箭头", snooze_second.toolTip())
        self.assertEqual(ignore_first.text(), "忽略")
        self.assertIn("清除截止时间", ignore_first.toolTip())
        self.assertEqual(
            [action.text() for action in snooze_second.menu().actions()],
            ["15分钟后", "1小时后", "晚上8点", "明天上午9点"],
        )

        complete_first.click()
        snooze_second.click()
        ignore_first.click()

        self.assertEqual(completed, [[1]])
        self.assertEqual(snoozed, [([2], timedelta(hours=1))])
        self.assertEqual(ignored, [[1]])

    def test_snooze_menu_keeps_alternative_duration_separate_from_primary(self) -> None:
        dialog = NotificationDialog([(make_todo(1, "第一项"), True)])
        self.addCleanup(dialog.close)
        snoozed: list[tuple[list[int], timedelta]] = []
        dialog.snooze_requested.connect(
            lambda ids, duration: snoozed.append((ids, duration))
        )

        snooze_action = dialog.findChild(QToolButton, "notificationSnooze_1")
        self.assertIsNotNone(snooze_action)
        fifteen_minute_action = next(
            action
            for action in snooze_action.menu().actions()
            if action.text() == "15分钟后"
        )

        fifteen_minute_action.trigger()

        self.assertEqual(snoozed, [([1], timedelta(minutes=15))])

    def test_due_text_includes_absolute_and_relative_time(self) -> None:
        todo = make_todo(1, "相对时间")
        todo["dueDate"] = "2026-08-06T10:00:00+00:00"
        dialog = NotificationDialog([(todo, False)])
        self.addCleanup(dialog.close)

        before_due = dialog._format_due_text(
            todo,
            datetime(2026, 8, 6, 9, 55, tzinfo=timezone.utc),
        )
        after_due = dialog._format_due_text(
            todo,
            datetime(2026, 8, 6, 10, 12, tzinfo=timezone.utc),
        )

        self.assertIn("截止时间:", before_due)
        self.assertIn("还有 5分", before_due)
        self.assertIn("已超时 12分", after_due)

    def test_relative_time_timer_refreshes_all_open_rows(self) -> None:
        dialog = NotificationDialog(
            [(make_todo(1, "第一项"), True), (make_todo(2, "第二项"), False)]
        )
        self.addCleanup(dialog.close)
        self.assertTrue(dialog._relative_time_timer.isActive())
        self.assertEqual(dialog._relative_time_timer.interval(), 1000)

        with patch.object(
            dialog,
            "_format_due_text",
            side_effect=["第一项已刷新", "第二项已刷新"],
        ) as formatter:
            dialog._relative_time_timer.timeout.emit()

        self.assertEqual(dialog._task_rows[1]["detail_label"].text(), "第一项已刷新")
        self.assertEqual(dialog._task_rows[2]["detail_label"].text(), "第二项已刷新")
        self.assertEqual(formatter.call_count, 2)
        first_now = formatter.call_args_list[0].args[1]
        second_now = formatter.call_args_list[1].args[1]
        self.assertIs(first_now, second_now)

    def test_common_three_task_dialog_expands_before_scrolling(self) -> None:
        dialog = NotificationDialog(
            [(make_todo(todo_id, f"任务{todo_id}"), True) for todo_id in (1, 2, 3)]
        )
        self.addCleanup(dialog.close)

        self.assertGreaterEqual(dialog.tasks_scroll.minimumHeight(), 180)
        self.assertLessEqual(dialog.tasks_scroll.minimumHeight(), 320)
        self.assertEqual(
            dialog.tasks_scroll.minimumHeight(), dialog.tasks_scroll.maximumHeight()
        )


class FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class FakeNotificationDialog:
    instances = []

    def __init__(self, requests, parent=None) -> None:
        self.requests = []
        self.show_count = 0
        self.hide_count = 0
        self.exec_count = 0
        self.closed = False
        self.visible = False
        self.complete_requested = FakeSignal()
        self.snooze_requested = FakeSignal()
        self.ignore_requested = FakeSignal()
        self.finished = FakeSignal()
        if isinstance(requests, list):
            self.add_or_update_tasks(requests)
        else:
            self.add_or_update_tasks([(requests, True)])
        self.instances.append(self)

    def add_or_update_tasks(self, requests) -> None:
        by_id = {int(todo["id"]): (todo, is_due) for todo, is_due in self.requests}
        for todo, is_due in requests:
            todo_id = int(todo["id"])
            previous = by_id.get(todo_id)
            by_id[todo_id] = (todo, bool(is_due or (previous and previous[1])))
        self.requests = list(by_id.values())

    def task_ids(self) -> list[int]:
        return [int(todo["id"]) for todo, _ in self.requests]

    def remove_tasks(self, task_ids) -> None:
        removed = {int(todo_id) for todo_id in task_ids}
        self.requests = [item for item in self.requests if int(item[0]["id"]) not in removed]

    def show(self) -> None:
        self.show_count += 1
        self.visible = True

    def hide(self) -> None:
        self.hide_count += 1
        self.visible = False

    def exec(self) -> QDialog.DialogCode:
        self.exec_count += 1
        return QDialog.DialogCode.Rejected

    def raise_(self) -> None:
        pass

    def activateWindow(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class NotificationBatchIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_due_tasks_share_one_non_modal_in_app_window(self) -> None:
        now = datetime.now(timezone.utc)
        due_date = (now - timedelta(minutes=1)).isoformat()
        tasks = [make_todo(todo_id, f"任务{todo_id}") for todo_id in (1, 2, 3)]
        for todo in tasks:
            todo["dueDate"] = due_date

        FakeNotificationDialog.instances = []
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos") as save_mock,
            patch("todo_app.main_window.play_sound_effect") as sound_mock,
            patch("todo_app.main_window.NotificationDialog", FakeNotificationDialog),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            window._ensure_window_visible_for_notification = MagicMock()
            window.tray_icon.showMessage = MagicMock()
            self.addCleanup(self._close_window, window)
            window.todos = tasks
            window.update_list_widget()

            window.tick_update()

            self.assertEqual(len(FakeNotificationDialog.instances), 1)
            dialog = FakeNotificationDialog.instances[0]
            self.assertEqual(dialog.task_ids(), [1, 2, 3])
            self.assertEqual(dialog.show_count, 1)
            self.assertEqual(dialog.exec_count, 0)
            self.assertEqual(sound_mock.call_count, 1)
            self.assertTrue(all(todo["notifiedForDue"] for todo in tasks))
            window.tray_icon.showMessage.assert_not_called()

            fourth = make_todo(4, "任务4")
            fourth["dueDate"] = due_date
            window.todos.append(fourth)
            window.update_list_widget()
            window.tick_update()

            self.assertEqual(len(FakeNotificationDialog.instances), 1)
            self.assertEqual(dialog.task_ids(), [1, 2, 3, 4])
            self.assertEqual(dialog.show_count, 1)
            self.assertEqual(sound_mock.call_count, 2)
            self.assertGreaterEqual(save_mock.call_count, 2)
            window.tray_icon.showMessage.assert_not_called()

    def test_filtered_out_incomplete_task_still_triggers_in_app_reminder(self) -> None:
        task = make_todo(1, "筛选外任务")
        task["dueDate"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        FakeNotificationDialog.instances = []
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos"),
            patch("todo_app.main_window.play_sound_effect"),
            patch("todo_app.main_window.NotificationDialog", FakeNotificationDialog),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            window._ensure_window_visible_for_notification = MagicMock()
            self.addCleanup(self._close_window, window)
            window.todos = [task]
            window.filter_combo.setCurrentText("已完成")
            window.update_list_widget()

            window.tick_update()

            self.assertTrue(task["notifiedForDue"])
            self.assertEqual(len(FakeNotificationDialog.instances), 1)
            self.assertEqual(FakeNotificationDialog.instances[0].task_ids(), [1])

    def test_closed_notification_dialog_is_deleted_from_parent(self) -> None:
        task = make_todo(1, "关闭后释放")
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos"),
            patch("todo_app.main_window.play_sound_effect"),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            window._ensure_window_visible_for_notification = MagicMock()
            self.addCleanup(self._close_window, window)

            window._show_notification_batch([(task, True)])
            dialog = window._notification_dialog
            self.assertIsNotNone(dialog)
            self.assertEqual(len(window.findChildren(NotificationDialog)), 1)

            dialog.reject()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()

            self.assertIsNone(window._notification_dialog)
            self.assertEqual(window.findChildren(NotificationDialog), [])

    def test_minimize_to_tray_preserves_and_restores_notification_batch(self) -> None:
        task = make_todo(1, "保留提醒")
        FakeNotificationDialog.instances = []
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos"),
            patch("todo_app.main_window.NotificationDialog", FakeNotificationDialog),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            self.addCleanup(self._close_window, window)
            dialog = FakeNotificationDialog([(task, True)], window)
            window._notification_dialog = dialog
            window.tray_icon.isVisible = MagicMock(return_value=True)
            window.tray_icon.showMessage = MagicMock()
            event = QCloseEvent()

            window.closeEvent(event)

            self.assertFalse(event.isAccepted())
            self.assertIs(window._notification_dialog, dialog)
            self.assertFalse(dialog.closed)
            window.tray_icon.showMessage.assert_not_called()

            window.toggle_window_visibility()
            self.assertEqual(dialog.show_count, 1)

    def test_minimize_to_tray_does_not_show_system_message(self) -> None:
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos"),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            self.addCleanup(self._close_window, window)
            window.tray_icon.showMessage = MagicMock()

            window._minimize_to_tray()

            self.assertTrue(window.isHidden())
            window.tray_icon.showMessage.assert_not_called()

    def test_tray_menu_hides_and_restores_notification_batch(self) -> None:
        task = make_todo(1, "随主窗口隐藏")
        FakeNotificationDialog.instances = []
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos"),
            patch("todo_app.main_window.NotificationDialog", FakeNotificationDialog),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            self.addCleanup(self._close_window, window)
            dialog = FakeNotificationDialog([(task, True)], window)
            window._notification_dialog = dialog
            dialog.show()
            window.show()
            self.app.processEvents()

            window.toggle_window_visibility()

            self.assertTrue(window.isHidden())
            self.assertIs(window._notification_dialog, dialog)
            self.assertFalse(dialog.closed)
            self.assertEqual(dialog.hide_count, 1)
            self.assertFalse(dialog.visible)

            window.toggle_window_visibility()

            self.assertTrue(window.isVisible())
            self.assertEqual(dialog.show_count, 2)
            self.assertTrue(dialog.visible)

    def test_requested_actions_update_only_requested_tasks_once(self) -> None:
        tasks = [make_todo(todo_id, f"任务{todo_id}") for todo_id in (1, 2, 3)]
        FakeNotificationDialog.instances = []
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos") as save_mock,
            patch("todo_app.main_window.NotificationDialog", FakeNotificationDialog),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            self.addCleanup(self._close_window, window)
            window.todos = tasks
            window.update_list_widget = MagicMock()
            dialog = FakeNotificationDialog([(todo, True) for todo in tasks], window)
            window._notification_dialog = dialog

            window._handle_notification_complete([1, 2])

            self.assertTrue(tasks[0]["completed"])
            self.assertTrue(tasks[1]["completed"])
            self.assertFalse(tasks[2]["completed"])
            self.assertEqual(dialog.task_ids(), [3])
            self.assertEqual(save_mock.call_count, 1)
            self.assertEqual(window.update_list_widget.call_count, 1)

            window.toggle_complete_todo(3)
            self.assertEqual(dialog.task_ids(), [])

    def test_snooze_handler_keeps_other_tasks_unchanged(self) -> None:
        first = make_todo(1, "任务1")
        second = make_todo(2, "任务2")
        first_before = first.copy()
        FakeNotificationDialog.instances = []
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos") as save_mock,
            patch("todo_app.main_window.NotificationDialog", FakeNotificationDialog),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            self.addCleanup(self._close_window, window)
            window.todos = [first, second]
            window.update_list_widget = MagicMock()
            dialog = FakeNotificationDialog([(first, True), (second, True)], window)
            window._notification_dialog = dialog

            window._handle_notification_snooze([2], timedelta(minutes=15))

            self.assertEqual(first, first_before)
            self.assertIsNotNone(second["snoozeUntil"])
            self.assertEqual(dialog.task_ids(), [1])
            self.assertEqual(save_mock.call_count, 1)
            self.assertEqual(window.update_list_widget.call_count, 1)

    def test_tasks_can_be_snoozed_independently_with_different_durations(self) -> None:
        first = make_todo(1, "任务1")
        second = make_todo(2, "任务2")
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos") as save_mock,
            patch("todo_app.main_window.NotificationDialog", FakeNotificationDialog),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            self.addCleanup(self._close_window, window)
            window.todos = [first, second]
            window.update_list_widget = MagicMock()
            dialog = FakeNotificationDialog([(first, True), (second, True)], window)
            window._notification_dialog = dialog

            window._handle_notification_snooze([1], timedelta(minutes=15))
            first_after_snooze = first.copy()
            window._handle_notification_snooze([2], timedelta(hours=1))

            self.assertEqual(first, first_after_snooze)
            first_until = datetime.fromisoformat(first["snoozeUntil"])
            second_until = datetime.fromisoformat(second["snoozeUntil"])
            self.assertGreater(second_until - first_until, timedelta(minutes=44))
            self.assertEqual(dialog.task_ids(), [])
            self.assertEqual(save_mock.call_count, 2)
            self.assertEqual(window.update_list_widget.call_count, 2)

    def test_ignore_clears_schedule_but_preserves_task_and_preference(self) -> None:
        task = make_todo(1, "保留但清除时间")
        task.update(
            {
                "reminderOffset": 900,
                "snoozeUntil": "2026-08-06T12:00:00+00:00",
                "notifiedForReminder": True,
                "notifiedForDue": True,
                "lastNotifiedAt": "2026-08-06T10:00:00+00:00",
            }
        )
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.save_todos") as save_mock,
            patch("todo_app.main_window.NotificationDialog", FakeNotificationDialog),
        ):
            window = ModernTodoAppWindow()
            window.master_timer.stop()
            self.addCleanup(self._close_window, window)
            window.todos = [task]
            window.update_list_widget = MagicMock()
            window._show_notification_batch = MagicMock()
            dialog = FakeNotificationDialog([(task, True)], window)
            window._notification_dialog = dialog

            window._handle_notification_ignore([1])

            self.assertIsNone(task["dueDate"])
            self.assertIsNone(task["snoozeUntil"])
            self.assertFalse(task["notifiedForReminder"])
            self.assertFalse(task["notifiedForDue"])
            self.assertEqual(task["reminderOffset"], 900)
            self.assertFalse(task["completed"])
            self.assertEqual(task["lastNotifiedAt"], "2026-08-06T10:00:00+00:00")
            self.assertEqual(window.todos, [task])
            self.assertEqual(dialog.task_ids(), [])
            self.assertEqual(save_mock.call_count, 1)
            self.assertEqual(window.update_list_widget.call_count, 1)

            window.tick_update()

            window._show_notification_batch.assert_not_called()
            self.assertEqual(save_mock.call_count, 1)

    def _close_window(self, window: ModernTodoAppWindow) -> None:
        window.master_timer.stop()
        window._quitting_app = True
        window.tray_icon.hide()
        window.close()


if __name__ == "__main__":
    unittest.main()
