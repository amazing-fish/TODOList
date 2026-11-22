"""Phase 2 信息架构与交互体验重构测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QEnterEvent, QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QPushButton  # noqa: E402

from todo_app.dialogs import TaskEditDialog  # noqa: E402
from todo_app.main_window import ModernTodoAppWindow  # noqa: E402
from todo_app.storage import StorageStatus  # noqa: E402
from todo_app.widgets import TodoItemWidget  # noqa: E402


def _make_task(
    todo_id: int,
    text: str,
    *,
    priority: str = "中",
    completed: bool = False,
    due_date: str | None = None,
) -> dict:
    return {
        "id": todo_id,
        "text": text,
        "priority": priority,
        "completed": completed,
        "dueDate": due_date,
        "reminderOffset": 0,
        "createdAt": "2026-11-20T08:00:00+00:00",
        "snoozeUntil": None,
        "notifiedForReminder": False,
        "notifiedForDue": False,
        "lastNotifiedAt": None,
    }


class Phase2UxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.settings_store: dict[str, object] = {}
        self.fake_settings = MagicMock()
        self.fake_settings.value.side_effect = lambda key, default=None: self.settings_store.get(
            key, default
        )
        self.fake_settings.setValue.side_effect = lambda key, val: self.settings_store.__setitem__(
            key, val
        )
        settings_patcher = patch("todo_app.main_window.QSettings", return_value=self.fake_settings)
        settings_patcher.start()
        self.addCleanup(settings_patcher.stop)

    def _create_window(
        self,
        todos: list[dict] | None = None,
        *,
        storage_status: StorageStatus | None = None,
    ) -> ModernTodoAppWindow:
        initial = [item.copy() for item in (todos or [])]
        with (
            patch("todo_app.main_window.load_todos", return_value=initial),
            patch("todo_app.main_window.save_todos", return_value=True),
        ):
            window = ModernTodoAppWindow()
        window.master_timer.stop()
        if storage_status is not None:
            window._storage_status = storage_status
            window._sync_storage_warning_banner()
        self.addCleanup(self._close_window, window)
        return window

    @staticmethod
    def _close_window(window: ModernTodoAppWindow) -> None:
        window._quitting_app = True
        window.master_timer.stop()
        window.tray_icon.hide()
        window.close()
        window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()

    def test_inline_quick_add_creates_task_and_shift_enter_opens_prefilled_editor(self) -> None:
        window = self._create_window()
        window.show()
        self.app.processEvents()

        window.quick_add_input.setText("  买牛奶与面包  ")
        enter_event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.NoModifier,
        )
        with patch("todo_app.main_window.save_todos", return_value=True):
            window.eventFilter(window.quick_add_input, enter_event)

        self.assertEqual(len(window.todos), 1)
        self.assertEqual(window.todos[0]["text"], "买牛奶与面包")
        self.assertEqual(window.todos[0]["priority"], "中")
        self.assertIsNone(window.todos[0]["dueDate"])
        self.assertEqual(window.quick_add_input.text(), "")

        window.quick_add_input.setText("起草季度汇报")
        shift_enter = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.ShiftModifier,
        )
        captured_initial: list[str] = []

        def _fake_add_dialog(initial_text: str = "") -> bool:
            captured_initial.append(initial_text)
            return True

        window.show_add_task_dialog = _fake_add_dialog  # type: ignore[method-assign]
        window.eventFilter(window.quick_add_input, shift_enter)
        self.assertEqual(captured_initial, ["起草季度汇报"])
        self.assertEqual(window.quick_add_input.text(), "")

    def test_inline_quick_add_blocks_write_in_corrupt_read_only_mode(self) -> None:
        read_only_status = StorageStatus(
            healthy=False,
            read_only=True,
            source=Path("todos.json"),
            message="主文件已损坏，只读保护中",
            data_file=Path("todos.json"),
            backup_file=Path("todos.json.bak"),
        )
        window = self._create_window(storage_status=read_only_status)
        window.quick_add_input.setText("不应写入")
        with (
            patch("todo_app.main_window.save_todos") as save_mock,
            patch("todo_app.main_window.QMessageBox.warning") as warn_mock,
        ):
            window._submit_quick_add()
        self.assertEqual(window.todos, [])
        save_mock.assert_not_called()
        warn_mock.assert_called_once()

    def test_search_status_summary_and_empty_reset_flow(self) -> None:
        overdue_due = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        todos = [
            _make_task(1, "准备 周报 PPT", due_date=overdue_due),
            _make_task(2, "购买咖啡豆"),
            _make_task(3, "已归档会议纪要", completed=True),
        ]
        window = self._create_window(todos)
        window.show()
        self.app.processEvents()

        self.assertEqual(window.status_summary_label.text(), "待办 2 · 逾期 1")
        self.assertIn("待办 2 · 逾期 1", window.tray_icon.toolTip())

        window.search_input.setText("周报")
        self.app.processEvents()
        self.assertEqual(set(window._todo_widgets_by_id), {1})

        window.search_input.setText("不存在的关键词")
        self.app.processEvents()
        self.assertEqual(window._todo_widgets_by_id, {})
        self.assertIsNotNone(window._empty_reset_button)
        self.assertTrue(window._empty_reset_button.isVisible())

        window._empty_reset_button.click()
        self.app.processEvents()
        self.assertEqual(window.filter_combo.currentText(), "全部")
        self.assertEqual(window.search_input.text(), "")
        self.assertEqual(set(window._todo_widgets_by_id), {1, 2, 3})

    def test_pin_state_persists_and_survives_temporary_foreground_restore(self) -> None:
        window = self._create_window()
        window.show()
        self.app.processEvents()

        window.pin_button.click()
        self.assertTrue(window._always_on_top)
        self.assertTrue(self.settings_store["windowAlwaysOnTop"])
        self.assertTrue(bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))

        window._restore_window_stays_on_top_flag()
        self.assertTrue(bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))

        reopened = self._create_window()
        self.assertTrue(reopened._always_on_top)
        self.assertTrue(reopened.pin_button.isChecked())
        self.assertTrue(bool(reopened.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))

    def test_undo_toast_restores_delete_complete_and_clear_due(self) -> None:
        due = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        todos = [
            _make_task(10, "第一项删除测试", due_date=due),
            _make_task(20, "第二项完成测试", due_date=due),
        ]
        window = self._create_window(todos)
        window.filter_combo.setCurrentText("未完成")
        window.show()
        self.app.processEvents()

        with patch("todo_app.main_window.save_todos", return_value=True):
            # 1. 删除免弹窗确认并可撤销恢复到原索引
            window.handle_delete_request(10)
            self.assertEqual([t["id"] for t in window.todos], [20])
            self.assertTrue(window.undo_toast_bar.has_active_undo())
            self.assertTrue(window.undo_toast_bar.trigger_undo())
            self.assertEqual([t["id"] for t in window.todos], [10, 20])
            self.assertFalse(window.undo_toast_bar.has_active_undo())

            # 2. 未完成视图下勾选完成并可撤销
            window.toggle_complete_todo(20)
            self.assertTrue(next(t for t in window.todos if t["id"] == 20)["completed"])
            self.assertTrue(window.undo_toast_bar.has_active_undo())
            self.assertTrue(window.undo_toast_bar.trigger_undo())
            self.assertFalse(next(t for t in window.todos if t["id"] == 20)["completed"])

            # 3. 清除截止时间并可撤销恢复原调度字段
            window._handle_notification_ignore([10])
            restored_target = next(t for t in window.todos if t["id"] == 10)
            self.assertIsNone(restored_target["dueDate"])
            self.assertTrue(window.undo_toast_bar.has_active_undo())
            self.assertTrue(window.undo_toast_bar.trigger_undo())
            restored_target = next(t for t in window.todos if t["id"] == 10)
            self.assertEqual(restored_target["dueDate"], due)

    def test_notification_acknowledge_preserves_due_and_edit_opens_editor(self) -> None:
        due = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        task = _make_task(7, "续签服务器证书", due_date=due)
        window = self._create_window([task])
        window.hide()
        with patch("todo_app.main_window.play_sound_effect"):
            window._show_notification_batch([(task, True)])

        window._handle_notification_acknowledge([7])
        self.assertEqual(window.todos[0]["dueDate"], due)
        self.assertIsNone(window._notification_dialog)

        with patch.object(window, "handle_edit_request") as edit_mock:
            window._handle_notification_edit(7)
        self.assertTrue(window.isVisible())
        edit_mock.assert_called_once_with(7)

    def test_details_popup_allows_hover_in_and_text_selection_without_focus_steal(self) -> None:
        card = TodoItemWidget(
            _make_task(1, "第一行\n第二行详细内容可供复制")
        )
        card.setFixedSize(300, 110)
        card.show()
        self.app.processEvents()
        self.addCleanup(card.close)
        card.complete_button.setFocus()
        self.app.processEvents()
        focused = self.app.focusWidget()

        card.task_text_label.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()
        popup = card.task_details_popup
        self.assertTrue(popup.isVisible())
        self.assertFalse(popup.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertTrue(
            bool(popup.details_label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse)
        )
        self.assertIs(self.app.focusWidget(), focused)

        card.task_text_label.leaveEvent(QEvent(QEvent.Type.Leave))
        popup.enterEvent(QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
        self.assertFalse(card._details_hide_timer.isActive())
        card._hide_task_details_if_unhovered()
        self.assertTrue(popup.isVisible())

    def test_task_edit_dialog_presets_reminder_toggle_and_past_due_hint(self) -> None:
        dialog = TaskEditDialog(initial_text="快速展开内容")
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.task_input.toPlainText(), "快速展开内容")
        self.assertLessEqual(dialog.minimumWidth(), 360)
        self.assertFalse(dialog.reminder_combo.isEnabled())

        tonight_btn = dialog.findChild(QPushButton, "duePreset_tonight")
        self.assertIsNotNone(tonight_btn)
        tonight_btn.click()
        self.assertTrue(dialog.set_due_date_button.isChecked())
        self.assertTrue(dialog.reminder_combo.isEnabled())
        self.assertIsNotNone(dialog.get_task_data()["dueDate"])

        past_dt = datetime.now().astimezone() - timedelta(days=2)
        dialog.show()
        self.app.processEvents()
        dialog.date_edit.setDate(past_dt.date())
        dialog.time_edit.setTime(past_dt.time())
        dialog._refresh_due_warning()
        self.assertTrue(dialog.info_label.isVisible())
        self.assertIn("已逾期", dialog.info_label.text())

        with patch("todo_app.dialogs.QDialog.accept") as base_accept:
            ctrl_enter = QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Return,
                Qt.KeyboardModifier.ControlModifier,
            )
            self.assertTrue(dialog.eventFilter(dialog.task_input, ctrl_enter))
            base_accept.assert_called_once()


if __name__ == "__main__":
    unittest.main()
