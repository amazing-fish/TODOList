"""提醒位置与任务编辑焦点的生命周期回归测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QRect, QTimer, Qt, SIGNAL  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

from todo_app.dialogs import NotificationDialog, TaskEditDialog  # noqa: E402
from todo_app.main_window import ModernTodoAppWindow  # noqa: E402
from todo_app.theme import ThemeMode, get_theme_manager  # noqa: E402


def make_todo(todo_id: int) -> dict:
    return {
        "id": todo_id,
        "text": f"待处理任务 {todo_id}",
        "priority": "中",
        "completed": False,
        "dueDate": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "reminderOffset": 0,
        "createdAt": "2026-09-01T00:00:00+00:00",
        "snoozeUntil": None,
        "notifiedForReminder": False,
        "notifiedForDue": False,
        "lastNotifiedAt": None,
    }


class NotificationWindowUxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        for target, kwargs in (
            ("load_todos", {"return_value": []}),
            ("save_todos", {}),
            ("QSettings", {"return_value": MagicMock()}),
            ("play_sound_effect", {}),
        ):
            patcher = patch(f"todo_app.main_window.{target}", **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.window = ModernTodoAppWindow()
        self.window.master_timer.stop()
        self.window._force_window_foreground = MagicMock()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self._close_window)

    def _close_window(self) -> None:
        self.window._quitting_app = True
        self.window.tray_icon.hide()
        self.window.close()
        self.app.processEvents()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def _notify(self, *todo_ids: int) -> NotificationDialog:
        tasks = [make_todo(todo_id) for todo_id in todo_ids]
        self.window.todos.extend(tasks)
        self.window._show_notification_batch([(task, True) for task in tasks])
        self.app.processEvents()
        return self.window._notification_dialog

    def _run_editor(self, inspect, *, todo_id=None, accept=False) -> None:
        errors = []

        def execute(editor):
            def while_open():
                try:
                    self.assertIs(self.app.activeModalWidget(), editor)
                    self.assertTrue(editor.isVisible())
                    inspect(editor)
                    if accept:
                        editor.task_input.setPlainText("保存后的任务")
                        editor.accept()
                    else:
                        editor.reject()
                except BaseException as exc:
                    errors.append(exc)
                    editor.reject()

            QTimer.singleShot(0, while_open)
            return QDialog.exec(editor)

        with patch.object(TaskEditDialog, "exec", execute):
            if todo_id is None:
                self.window.show_add_task_dialog()
            else:
                self.window.handle_edit_request(todo_id)
        if errors:
            raise errors[0]
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.window.findChildren(TaskEditDialog), [])

    def test_one_hundred_editor_cycles_release_widgets_and_theme_connections(self) -> None:
        todo = make_todo(1)
        todo["dueDate"] = None
        self.window.todos = [todo]
        self.window.update_list_widget()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        theme = get_theme_manager()
        signal = SIGNAL("theme_changed(PyObject)")
        initial_receivers = theme.receivers(signal)
        initial_widgets = len(self.window.findChildren(QWidget))

        def inspect(editor):
            self.assertEqual(theme.receivers(signal), initial_receivers + 1)

        for index in range(100):
            with self.subTest(cycle=index):
                self._run_editor(inspect, todo_id=1 if index % 2 else None)
                self.assertEqual(len(self.window.findChildren(QWidget)), initial_widgets)
                self.assertEqual(theme.receivers(signal), initial_receivers)

    def test_notification_keeps_moved_position_after_refresh_resize_and_restore(self) -> None:
        dialog = self._notify(1)
        screen = dialog.screen().availableGeometry()
        self.assertTrue(screen.contains(dialog.frameGeometry()))
        dialog.move(screen.topLeft() + QPoint(30, 30))
        self.app.processEvents()
        position = dialog.pos()

        dialog._relative_time_timer.timeout.emit()
        self.assertEqual(dialog.pos(), position)
        self._notify(2)
        self.assertEqual(dialog.pos(), position)
        dialog.remove_tasks([2])
        self.app.processEvents()
        self.assertEqual(dialog.pos(), position)
        dialog.hide()
        dialog.show()
        self.app.processEvents()
        self.assertEqual(dialog.pos(), position)

    def test_restored_notification_is_corrected_into_available_screen(self) -> None:
        dialog = self._notify(1)
        screen = dialog.screen().availableGeometry()
        dialog.hide()
        dialog.move(screen.right() + 500, screen.bottom() + 500)
        dialog.show()
        self.app.processEvents()
        self.assertTrue(screen.contains(dialog.frameGeometry()))

    def test_screen_geometry_change_clamps_without_returning_to_parent_screen(self) -> None:
        dialog = self._notify(1)
        available = QRect(-1000, 0, 900, 700)
        second_screen = MagicMock()
        second_screen.availableGeometry.return_value = available
        with patch("todo_app.dialogs.QGuiApplication.screenAt", return_value=second_screen):
            dialog.move(-900, 30)
            position = dialog.pos()
            dialog.screen().availableGeometryChanged.emit(available)
            self.assertEqual(dialog.pos(), position)
            dialog.move(-300, 600)
            dialog.screen().availableGeometryChanged.emit(available)
            self.assertTrue(available.contains(dialog.frameGeometry()))

    def test_existing_reminders_yield_to_add_cancel_and_save(self) -> None:
        dialog = self._notify(1)
        for accept in (False, True, False):
            with self.subTest(accept=accept):
                self._run_editor(
                    lambda editor: self.assertFalse(dialog.isVisible()), accept=accept
                )
                self.assertIs(self.window._notification_dialog, dialog)
                self.assertTrue(dialog.isVisible())
                self.assertIsNone(self.app.activeModalWidget())
        self.assertEqual(len(self.window.todos), 2)
        self.assertEqual(self.window.todos[-1]["text"], "保存后的任务")

    def test_edit_removes_only_its_reminder_before_restoring_remaining_batch(self) -> None:
        dialog = self._notify(1, 2)
        self._run_editor(
            lambda editor: self.assertFalse(dialog.isVisible()), todo_id=1, accept=True
        )
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.task_ids(), [2])
        self.assertEqual(self.window.todos[0]["text"], "保存后的任务")

    def test_add_and_edit_sessions_reuse_untouched_cards_without_clearing_list(self) -> None:
        dialog = self._notify(1, 2)
        self.window.update_list_widget()
        untouched = self.window._todo_widgets_by_id[2]
        with (
            patch.object(self.window.list_widget, "clear", wraps=self.window.list_widget.clear) as clear,
            patch.object(untouched, "update_todo", wraps=untouched.update_todo) as update_untouched,
        ):
            self._run_editor(lambda editor: self.assertFalse(dialog.isVisible()), accept=True)
            self._run_editor(
                lambda editor: self.assertFalse(dialog.isVisible()), todo_id=1, accept=True
            )

        clear.assert_not_called()
        update_untouched.assert_not_called()
        self.assertIs(self.window._todo_widgets_by_id[2], untouched)
        self.assertEqual(self.window.list_widget.count(), 3)
        self.assertEqual(dialog.task_ids(), [2])

    def test_cancel_edit_does_not_save_or_change_existing_tasks(self) -> None:
        dialog = self._notify(1)
        before = [todo.copy() for todo in self.window.todos]
        with patch("todo_app.main_window.save_todos") as save:
            self._run_editor(
                lambda editor: editor.task_input.setPlainText("取消的修改"), todo_id=1
            )

        save.assert_not_called()
        self.assertEqual(self.window.todos, before)
        self.assertTrue(dialog.isVisible())

    def test_new_due_batch_during_editor_is_recorded_without_stealing_focus(self) -> None:
        def inspect(editor):
            self.window.todos = [make_todo(1), make_todo(2)]
            self.window.tick_update()
            dialog = self.window._notification_dialog
            self.assertEqual(dialog.task_ids(), [1, 2])
            self.assertFalse(dialog.isVisible())
            self.assertIs(self.app.activeModalWidget(), editor)
            self.assertTrue(all(todo["notifiedForDue"] for todo in self.window.todos))
            self.window._force_window_foreground.assert_not_called()

        self._run_editor(inspect)
        self.assertTrue(self.window._notification_dialog.isVisible())

    def test_existing_batch_can_grow_during_editor_without_resetting_position(self) -> None:
        dialog = self._notify(1)
        dialog.move(dialog.screen().availableGeometry().topLeft() + QPoint(30, 30))
        position = dialog.pos()

        def inspect(editor):
            self.assertIs(self._notify(2), dialog)
            self.assertFalse(dialog.isVisible())
            self.window.show_add_task_dialog()
            self.window.handle_edit_request(1)
            self.assertEqual(self.window.findChildren(TaskEditDialog), [editor])
            self.assertIs(self.app.activeModalWidget(), editor)

        self._run_editor(inspect)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.task_ids(), [1, 2])
        self.assertEqual(dialog.pos(), position)

    def test_editor_clears_temporary_topmost_timer_before_modal_execution(self) -> None:
        self.window._temporarily_force_window_on_top()

        def inspect(editor):
            self.assertFalse(self.window._on_top_restore_timer.isActive())
            self.assertFalse(self.window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

        self._run_editor(inspect)

    def test_editor_exception_releases_children_and_restores_reminders(self) -> None:
        dialog = self._notify(1)
        with patch.object(TaskEditDialog, "exec", side_effect=RuntimeError("编辑失败")):
            with self.assertRaisesRegex(RuntimeError, "编辑失败"):
                self.window.show_add_task_dialog()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(self.window.findChildren(TaskEditDialog), [])

    def test_tray_restore_during_editor_keeps_reminders_hidden(self) -> None:
        dialog = self._notify(1)

        def inspect(editor):
            self.window._minimize_to_tray()
            self.window.toggle_window_visibility()
            self.assertFalse(dialog.isVisible())
            self.assertIs(self.app.activeModalWidget(), editor)

        self._run_editor(inspect)
        self.assertTrue(dialog.isVisible())

    def test_editor_finish_does_not_restore_reminders_over_hidden_main_window(self) -> None:
        dialog = self._notify(1)
        self._run_editor(lambda editor: self.window._minimize_to_tray())
        self.assertFalse(dialog.isVisible())
        self.window.toggle_window_visibility()
        self.assertTrue(dialog.isVisible())

    def test_repeated_editors_release_qt_children(self) -> None:
        for _ in range(100):
            self._run_editor(lambda editor: None)

    def test_theme_changes_during_edit_keep_notification_hidden_and_positioned(self) -> None:
        manager = get_theme_manager()
        original = manager._detect_mode()
        self.addCleanup(manager._apply_mode, original)
        dialog = self._notify(1)
        dialog.move(dialog.screen().availableGeometry().topLeft() + QPoint(30, 30))
        position = dialog.pos()
        for mode in (ThemeMode.DARK, ThemeMode.LIGHT):
            def inspect(editor):
                manager._apply_mode(mode)
                self.assertFalse(dialog.isVisible())
                self.assertEqual(dialog._palette, manager.current_palette)
                self.assertEqual(editor._palette, manager.current_palette)

            self._run_editor(inspect)
            self.assertEqual(dialog.pos(), position)

    def test_notification_row_gaps_follow_both_themes(self) -> None:
        manager = get_theme_manager()
        original = manager._detect_mode()
        self.addCleanup(manager._apply_mode, original)
        dialog = self._notify(1, 2)
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            manager._apply_mode(mode)
            self.app.processEvents()
            first_row = dialog._task_rows[1]["widget"]
            gap = dialog.tasks_container.mapTo(
                dialog, QPoint(10, first_row.geometry().bottom() + 4)
            )
            image = dialog.grab().toImage()
            scale = image.devicePixelRatio()
            color = image.pixelColor(round(gap.x() * scale), round(gap.y() * scale))
            self.assertEqual(color.name(), manager.current_palette.background.lower())


if __name__ == "__main__":
    unittest.main()
