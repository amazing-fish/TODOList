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

    def test_complete_uses_selection_but_each_snooze_targets_its_own_task(self) -> None:
        dialog = NotificationDialog(
            [(make_todo(1, "第一项"), True), (make_todo(2, "第二项"), True)]
        )
        destroyed = []
        dialog.destroyed.connect(lambda: destroyed.append(True))
        second_checkbox = dialog.findChild(QCheckBox, "notificationSelect_2")
        self.assertIsNotNone(second_checkbox)
        second_checkbox.setChecked(False)
        completed: list[list[int]] = []
        snoozed: list[tuple[int, timedelta]] = []
        dialog.complete_requested.connect(completed.append)
        dialog.snooze_requested.connect(
            lambda todo_id, duration: snoozed.append((todo_id, duration))
        )

        dialog.complete_button.click()
        first_checkbox = dialog.findChild(QCheckBox, "notificationSelect_1")
        self.assertIsNotNone(first_checkbox)
        first_checkbox.setChecked(False)
        first_snooze = dialog.findChild(QPushButton, "notificationSnoozeDefault_1")
        self.assertIsNotNone(first_snooze)
        first_snooze.click()
        second_menu_button = dialog.findChild(
            QPushButton, "notificationSnoozeMenu_2"
        )
        self.assertIsNotNone(second_menu_button)
        second_menu_button.menu().actions()[1].trigger()

        self.assertEqual(completed, [[1]])
        self.assertEqual(
            snoozed,
            [
                (1, timedelta(minutes=15)),
                (2, timedelta(hours=1)),
            ],
        )

        dialog.show()
        self.app.processEvents()
        dialog.remove_tasks([1])
        self.assertEqual(dialog.task_ids(), [2])
        self.assertTrue(dialog.isVisible())
        dialog.remove_tasks([2])
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(destroyed, [True])

    def test_local_clock_snooze_options_keep_cross_day_semantics(self) -> None:
        dialog = NotificationDialog(
            [(make_todo(1, "晚上八点"), True), (make_todo(2, "明早九点"), True)]
        )
        self.addCleanup(dialog.close)
        requested: list[tuple[int, timedelta]] = []
        dialog.snooze_requested.connect(
            lambda todo_id, duration: requested.append((todo_id, duration))
        )
        fixed_now = datetime(
            2026, 7, 17, 21, 30, tzinfo=timezone(timedelta(hours=8))
        )

        with patch("todo_app.dialogs._local_now", return_value=fixed_now):
            dialog.snooze_8pm(1)
            dialog.snooze_tomorrow_9am(2)

        self.assertEqual(
            requested,
            [
                (1, timedelta(hours=22, minutes=30)),
                (2, timedelta(hours=11, minutes=30)),
            ],
        )

    def test_individual_snooze_preserves_epoch_millisecond_task_id(self) -> None:
        todo_id = 1_752_000_000_001
        dialog = NotificationDialog([(make_todo(todo_id, "大编号任务"), True)])
        self.addCleanup(dialog.close)
        requested: list[tuple[int, timedelta]] = []
        dialog.snooze_requested.connect(
            lambda emitted_id, duration: requested.append((emitted_id, duration))
        )

        dialog.snooze_default(todo_id)

        self.assertEqual(requested, [(todo_id, timedelta(minutes=15))])

    def test_common_three_task_batch_expands_before_scrolling(self) -> None:
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

    def test_batch_actions_update_only_requested_tasks_once(self) -> None:
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

    def test_individual_snoozes_use_different_durations_and_remove_each_row(self) -> None:
        first = make_todo(1, "任务1")
        second = make_todo(2, "任务2")
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

            window._handle_notification_snooze(1, timedelta(minutes=15))

            self.assertIsNotNone(first["snoozeUntil"])
            self.assertIsNone(second["snoozeUntil"])
            self.assertEqual(dialog.task_ids(), [2])
            window._handle_notification_snooze(2, timedelta(hours=1))

            self.assertIsNotNone(second["snoozeUntil"])
            first_target = datetime.fromisoformat(first["snoozeUntil"])
            second_target = datetime.fromisoformat(second["snoozeUntil"])
            self.assertAlmostEqual(
                (second_target - first_target).total_seconds(),
                timedelta(minutes=45).total_seconds(),
                delta=2,
            )
            self.assertEqual(dialog.task_ids(), [])
            self.assertEqual(save_mock.call_count, 2)
            self.assertEqual(window.update_list_widget.call_count, 2)

    def _close_window(self, window: ModernTodoAppWindow) -> None:
        window.master_timer.stop()
        window._quitting_app = True
        window.tray_icon.hide()
        window.close()


if __name__ == "__main__":
    unittest.main()
