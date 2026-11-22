import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from todo_app.autostart import (
    build_autostart_command,
    is_autostart_enabled,
    is_autostart_supported,
    set_autostart_enabled,
)
from todo_app.constants import DARK_THEME_COLORS, LIGHT_THEME_COLORS
from todo_app.main_window import ModernTodoAppWindow
from todo_app.settings_dialog import SettingsDialog
from todo_app.storage import StorageStatus
from todo_app.theme import ThemeManager, ThemeMode, ThemePreference


class _FakeRegistryBackend:
    def __init__(self, *, supported: bool = True) -> None:
        self.supported = supported
        self.values: dict[str, str] = {}

    def is_supported(self) -> bool:
        return self.supported

    def read_run_entry(self, name: str) -> str | None:
        return self.values.get(name)

    def write_run_entry(self, name: str, command: str) -> None:
        self.values[name] = command

    def delete_run_entry(self, name: str) -> None:
        self.values.pop(name, None)


class AutostartAndThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_autostart_toggle_with_fake_registry_backend(self) -> None:
        backend = _FakeRegistryBackend()
        self.assertTrue(is_autostart_supported(backend=backend))
        self.assertFalse(is_autostart_enabled(backend=backend))

        command = build_autostart_command(
            executable="C:/py/pythonw.exe",
            entry_script=Path("C:/app/main.py"),
            frozen=False,
        )
        self.assertIn("pythonw.exe", command)
        self.assertTrue(set_autostart_enabled(True, backend=backend, command=command))
        self.assertTrue(is_autostart_enabled(backend=backend))

        self.assertFalse(set_autostart_enabled(False, backend=backend))
        self.assertFalse(is_autostart_enabled(backend=backend))

    def test_theme_manager_explicit_preference_overrides_system(self) -> None:
        manager = ThemeManager()
        with patch.object(manager, "_detect_mode", return_value=ThemeMode.LIGHT):
            manager.set_preference(ThemePreference.SYSTEM)
            self.assertEqual(manager.current_palette, LIGHT_THEME_COLORS)

            manager.set_preference(ThemePreference.DARK)
            self.assertEqual(manager.current_palette, DARK_THEME_COLORS)

            manager._handle_color_scheme_changed(Qt.ColorScheme.Light)
            self.assertEqual(manager.current_palette, DARK_THEME_COLORS)

            manager.set_preference(ThemePreference.SYSTEM)
            self.assertEqual(manager.current_palette, LIGHT_THEME_COLORS)


class SettingsAndWindowWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _close_window(window: ModernTodoAppWindow) -> None:
        window.master_timer.stop()
        window._quitting_app = True
        window.tray_icon.hide()
        window.close()

    def _create_window(self, todos: list[dict] | None = None) -> ModernTodoAppWindow:
        settings = MagicMock()
        settings.value.return_value = None
        initial = todos if todos is not None else []
        with (
            patch("todo_app.main_window.load_todos", return_value=initial),
            patch("todo_app.main_window.save_todos", return_value=True),
            patch("todo_app.main_window.QSettings", return_value=settings),
        ):
            window = ModernTodoAppWindow()
        window.master_timer.stop()
        window.show()
        self.app.processEvents()
        self.addCleanup(self._close_window, window)
        return window

    def test_settings_dialog_signals_and_1h_dnd_feedback(self) -> None:
        dialog = SettingsDialog(
            theme_preference=ThemePreference.DARK,
            sound_enabled=False,
            dnd_enabled=False,
            autostart_supported=True,
            autostart_enabled=True,
            completed_count=2,
        )
        self.addCleanup(dialog.deleteLater)

        observed: list[tuple[str, object]] = []
        dialog.theme_preference_changed.connect(lambda v: observed.append(("theme", v)))
        dialog.sound_enabled_changed.connect(lambda v: observed.append(("sound", v)))
        dialog.dnd_one_hour_requested.connect(lambda: observed.append(("dnd_1h", True)))
        dialog.clear_completed_requested.connect(lambda: observed.append(("clear", True)))

        dialog.theme_combo.setCurrentIndex(1)
        dialog.sound_checkbox.setChecked(True)
        dialog.dnd_1h_button.click()
        dialog.clear_completed_button.click()

        self.assertTrue(dialog.dnd_checkbox.isChecked())
        self.assertIn("1小时", dialog.dnd_status_label.text())
        self.assertIn(("theme", "light"), observed)
        self.assertIn(("sound", True), observed)
        self.assertIn(("dnd_1h", True), observed)
        self.assertIn(("clear", True), observed)

    def test_window_autostart_disable_does_not_raise_false_warning(self) -> None:
        window = self._create_window([])
        with (
            patch("todo_app.main_window.set_autostart_enabled", return_value=False) as setter,
            patch("todo_app.main_window.QMessageBox.warning") as warn_mock,
        ):
            window._set_autostart_enabled(False)
            setter.assert_called_once_with(False)
            warn_mock.assert_not_called()

    def test_dnd_and_sound_gating_in_main_window(self) -> None:
        overdue_due = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        todo = {
            "id": 1,
            "text": "会议提醒",
            "priority": "高",
            "dueDate": overdue_due,
            "reminderOffset": 0,
            "completed": False,
            "createdAt": overdue_due,
            "snoozeUntil": None,
            "notifiedForReminder": False,
            "notifiedForDue": False,
            "lastNotifiedAt": None,
        }
        window = self._create_window([todo])
        with (
            patch("todo_app.main_window.save_todos", return_value=True),
            patch("todo_app.main_window.play_sound_effect") as sound_mock,
            patch.object(window, "_show_notification_batch") as batch_mock,
        ):
            window.enable_dnd_for_one_hour()
            self.assertTrue(window.is_dnd_active())
            self.assertIn("勿扰", window.status_summary_label.text())
            window.tick_update()
            batch_mock.assert_not_called()
            sound_mock.assert_not_called()
            self.assertFalse(window.todos[0]["notifiedForDue"])

            window._dnd_until_utc = datetime.now(timezone.utc) - timedelta(seconds=1)
            window.tick_update()
            self.assertFalse(window.is_dnd_active())
            batch_mock.assert_called_once()

        with (
            patch("todo_app.main_window.play_sound_effect") as sound_mock,
            patch("todo_app.main_window.NotificationDialog") as dialog_cls,
            patch.object(window, "_restore_notification_dialog"),
        ):
            dialog_cls.return_value = MagicMock()
            window.set_sound_enabled(False)
            window._show_notification_batch([(todo, True)])
            sound_mock.assert_not_called()

    def test_clear_completed_export_import_and_readonly_guards(self) -> None:
        todos = [
            {
                "id": 1,
                "text": "已完成任务",
                "priority": "低",
                "dueDate": None,
                "reminderOffset": -1,
                "completed": True,
                "createdAt": "2026-04-01T00:00:00+00:00",
            },
            {
                "id": 2,
                "text": "进行中任务",
                "priority": "高",
                "dueDate": None,
                "reminderOffset": -1,
                "completed": False,
                "createdAt": "2026-04-02T00:00:00+00:00",
            },
        ]
        window = self._create_window(todos)
        with patch("todo_app.main_window.save_todos", return_value=True):
            removed = window.clear_completed_todos()
            self.assertEqual(removed, 1)
            self.assertEqual([t["id"] for t in window.todos], [2])

            window.undo_toast_bar.trigger_undo()
            self.assertEqual([t["id"] for t in window.todos], [1, 2])

            with tempfile.TemporaryDirectory() as tmp_dir:
                export_path = Path(tmp_dir) / "backup.json"
                backup_path = Path(tmp_dir) / "backup.json.bak"
                exported_count = window.export_todos_to_file(export_path)
                self.assertEqual(exported_count, 2)
                payload = json.loads(export_path.read_text(encoding="utf-8"))
                self.assertEqual(len(payload["todos"]), 2)

                imported_count = window.import_todos_from_file(export_path)
                self.assertEqual(imported_count, 2)
                self.assertEqual(len(window.todos), 4)
                self.assertEqual(len({t["id"] for t in window.todos}), 4)

                window.undo_toast_bar.trigger_undo()
                self.assertEqual(len(window.todos), 2)

                window._storage_status = StorageStatus(
                    healthy=False,
                    read_only=True,
                    source=backup_path,
                    message="只读测试",
                    data_file=export_path,
                    backup_file=backup_path,
                )
                # 禁止覆盖正在使用的数据文件及备份
                with self.assertRaises(ValueError):
                    window.export_todos_to_file(export_path)
                with self.assertRaises(ValueError):
                    window.export_todos_to_file(backup_path)

                # 只读保护模式下仍允许导出到独立路径，但拒绝导入和清理
                alt_export = Path(tmp_dir) / "safe-export.json"
                self.assertEqual(window.export_todos_to_file(alt_export), 2)
                with self.assertRaises(RuntimeError):
                    window.clear_completed_todos()
                with self.assertRaises(RuntimeError):
                    window.import_todos_from_file(export_path)

    def test_import_validation_persist_failure_rollback_and_scoped_undo(self) -> None:
        todos = [
            {
                "id": 1,
                "text": "已完成任务",
                "priority": "低",
                "dueDate": None,
                "reminderOffset": -1,
                "completed": True,
                "createdAt": "2026-04-01T00:00:00+00:00",
            },
            {
                "id": 2,
                "text": "保留任务",
                "priority": "高",
                "dueDate": None,
                "reminderOffset": -1,
                "completed": False,
                "createdAt": "2026-04-02T00:00:00+00:00",
                "notifiedForDue": False,
            },
        ]
        window = self._create_window(todos)
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_json = Path(tmp_dir) / "bad.json"
            bad_json.write_text(json.dumps([{"id": 9, "text": ["not-a-str"]}]), encoding="utf-8")
            with self.assertRaises(ValueError):
                window.import_todos_from_file(bad_json)
            self.assertEqual(len(window.todos), 2)

            with patch.object(window, "_persist_todos", return_value=False):
                with self.assertRaises(RuntimeError):
                    window.clear_completed_todos()
                self.assertEqual(len(window.todos), 2)

            with patch.object(window, "_persist_todos", return_value=True):
                window.clear_completed_todos()
                # 清理期间另一条任务的通知标记发生变化，撤销清理不得覆盖它
                window.todos[0]["notifiedForDue"] = True
                window.undo_toast_bar.trigger_undo()
                preserved = next(t for t in window.todos if t["id"] == 2)
                self.assertTrue(preserved["notifiedForDue"])

            # 校验 reminderOffset=null 与非字符串 snoozeUntil 被拒绝，且无时区 dueDate 自动归一化为 UTC
            null_offset = Path(tmp_dir) / "null_offset.json"
            null_offset.write_text(
                json.dumps([{"id": 10, "text": "x", "reminderOffset": None}]),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                window.import_todos_from_file(null_offset)

            bad_snooze = Path(tmp_dir) / "bad_snooze.json"
            bad_snooze.write_text(
                json.dumps([{"id": 11, "text": "y", "snoozeUntil": 12345}]),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                window.import_todos_from_file(bad_snooze)

            naive_due = Path(tmp_dir) / "naive_due.json"
            naive_due.write_text(
                json.dumps([{"id": 12, "text": "带无时区时间", "dueDate": "2026-11-22T09:00:00", "reminderOffset": 0}]),
                encoding="utf-8",
            )
            with patch.object(window, "_persist_todos", return_value=True):
                self.assertEqual(window.import_todos_from_file(naive_due), 1)
                imported_item = next(t for t in window.todos if t["text"] == "带无时区时间")
                self.assertEqual(imported_item["dueDate"], "2026-11-22T09:00:00+00:00")

    def test_dnd_expiration_updates_open_settings_dialog_and_prompts_flush_undo(self) -> None:
        window = self._create_window(
            [
                {
                    "id": 1,
                    "text": "已完成测试",
                    "priority": "中",
                    "dueDate": None,
                    "reminderOffset": -1,
                    "completed": True,
                    "createdAt": "2026-04-01T00:00:00+00:00",
                }
            ]
        )
        window.enable_dnd_for_one_hour()
        dlg = SettingsDialog(
            dnd_enabled=True,
            dnd_status_text=window.dnd_status_text(),
            completed_count=1,
            parent=window,
        )
        self.addCleanup(dlg.deleteLater)
        window._settings_dialog = dlg
        window._dnd_until_utc = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.assertFalse(window.is_dnd_active())
        self.assertFalse(dlg.dnd_checkbox.isChecked())
        self.assertIn("未开启", dlg.dnd_status_label.text())
        window._settings_dialog = None

        with (
            patch.object(window, "_persist_todos", return_value=True),
            patch(
                "todo_app.main_window.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
        ):
            dlg2 = SettingsDialog(completed_count=1, parent=window)
            self.addCleanup(dlg2.deleteLater)
            window._prompt_clear_completed_todos(dlg2)
            self.assertIsNotNone(window._deferred_undo_toast)
            window._flush_deferred_undo_toast()
            self.assertTrue(window.undo_toast_bar.has_active_undo())

    def test_narrow_320px_header_controls_fit_without_clipping_buttons(self) -> None:
        window = self._create_window([])
        window.resize(320, 640)
        self.app.processEvents()
        self.assertLessEqual(window.width(), 320)
        self.assertGreater(window.settings_button.width(), 20)
        self.assertGreater(window.pin_button.width(), 20)
        self.assertEqual(window.add_button.width(), 36)

    def test_dnd_keeps_retained_notification_hidden_and_restores_on_expiry(self) -> None:
        due = "2030-05-01T09:00:00+00:00"
        todo = {
            "id": 501,
            "text": "勿扰保留提醒批",
            "priority": "高",
            "dueDate": due,
            "reminderOffset": 0,
            "completed": False,
            "createdAt": "2030-04-30T09:00:00+00:00",
            "snoozeUntil": None,
            "notifiedForReminder": True,
            "notifiedForDue": True,
            "lastNotifiedAt": due,
        }
        window = self._create_window([todo])
        with (
            patch("todo_app.main_window.play_sound_effect"),
            patch("todo_app.main_window.save_todos", return_value=True),
        ):
            window._show_notification_batch([(window.todos[0], True)])
            self.assertTrue(window._notification_dialog.isVisible())

            # 隐藏主窗口后启用 1 小时勿扰，从托盘恢复主窗口时不得重新弹出已保留的通知窗
            window._hide_notification_dialog()
            window.hide()
            window.enable_dnd_for_one_hour()
            window.toggle_window_visibility()
            self.assertTrue(window.isVisible())
            self.assertFalse(window._notification_dialog.isVisible())
            self.assertIn(501, window._notification_dialog._task_rows)

            # 勿扰到期即使无新触发任务，tick_update 也应主动恢复保留的通知批
            window._dnd_until_utc = datetime.now(timezone.utc) - timedelta(seconds=1)
            window.tick_update()
            self.assertFalse(window.is_dnd_active())
            self.assertTrue(window._notification_dialog.isVisible())

    def test_import_validates_offsets_created_at_and_export_protects_hardlinks(self) -> None:
        import os

        window = self._create_window([])
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)

            # 1. 非法/超范围 reminderOffset 与组合溢出的 reminderOffset 必须被拒收
            bad_offset_1 = tmp_root / "bad_offset_huge.json"
            bad_offset_1.write_text(
                json.dumps([{"text": "bad", "reminderOffset": 10**12}]),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                window.import_todos_from_file(bad_offset_1)

            bad_offset_2 = tmp_root / "bad_offset_min_date.json"
            bad_offset_2.write_text(
                json.dumps(
                    [
                        {
                            "text": "overflow",
                            "dueDate": "0001-01-01T00:00:00+00:00",
                            "reminderOffset": 86400,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                window.import_todos_from_file(bad_offset_2)

            # 2. 超 UTC 范围 createdAt 在提交前即被拒收；合法带偏移 createdAt 规范化为 UTC
            bad_created = tmp_root / "bad_created.json"
            bad_created.write_text(
                json.dumps([{"text": "bad-created", "createdAt": "0001-01-01T00:00:00+08:00"}]),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                window.import_todos_from_file(bad_created)

            good_file = tmp_root / "good_with_inf_id.json"
            good_file.write_text(
                '[{"id": 1e309, "text": "非有限ID任务", "createdAt": "2026-11-22T10:00:00+08:00", "reminderOffset": 300}]',
                encoding="utf-8",
            )
            with patch.object(window, "_persist_todos", return_value=True):
                imported = window.import_todos_from_file(good_file)
            self.assertEqual(imported, 1)
            self.assertIsInstance(window.todos[0]["id"], int)
            self.assertEqual(window.todos[0]["createdAt"], "2026-11-22T02:00:00+00:00")

            # 3. 硬链接指向 active DATA_FILE 时 export_todos_to_file 通过 samefile 保护拒绝覆盖
            data_target = tmp_root / "active_todos.json"
            data_target.write_text("[]", encoding="utf-8")
            hardlink_target = tmp_root / "alias_export.json"
            os.link(data_target, hardlink_target)
            window._storage_status = StorageStatus(
                healthy=True,
                read_only=False,
                source=data_target,
                message="",
                data_file=data_target,
                backup_file=None,
            )
            with self.assertRaises(ValueError):
                window.export_todos_to_file(hardlink_target)
            self.assertEqual(data_target.read_text(encoding="utf-8"), "[]")

            # 4. 导出原子写：替换失败时保持既有目标文件不被截断且无残留 .tmp 文件
            safe_export = tmp_root / "safe.json"
            safe_export.write_text("PRIOR_CONTENT", encoding="utf-8")
            with patch("todo_app.main_window.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    window.export_todos_to_file(safe_export)
            self.assertEqual(safe_export.read_text(encoding="utf-8"), "PRIOR_CONTENT")
            self.assertEqual(list(tmp_root.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
