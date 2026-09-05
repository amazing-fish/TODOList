"""待办数据原子写入与损坏恢复测试。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from todo_app import storage


def _todo(todo_id: int, text: str) -> dict[str, object]:
    return {
        "id": todo_id,
        "text": text,
        "createdAt": "2026-07-31T00:00:00+00:00",
        "completed": False,
        "priority": "中",
        "dueDate": None,
        "reminderOffset": 0,
        "snoozeUntil": None,
        "lastNotifiedAt": None,
        "notifiedForReminder": False,
        "notifiedForDue": False,
    }


class StorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_file = Path(self.temp_dir.name) / "todos.json"
        self.backup_file = Path(f"{self.data_file}.bak")
        self.data_file_patcher = patch.object(storage, "DATA_FILE", self.data_file)
        self.data_file_patcher.start()

    def tearDown(self) -> None:
        self.data_file_patcher.stop()
        self.temp_dir.cleanup()

    def _write_json(self, path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )

    def _temp_files(self) -> list[Path]:
        return list(self.data_file.parent.glob(".*.tmp"))

    def test_first_save_writes_main_file_without_backup(self) -> None:
        todos = [_todo(1, "首次写入")]

        storage.save_todos(todos)

        self.assertEqual(json.loads(self.data_file.read_text(encoding="utf-8")), todos)
        self.assertFalse(self.backup_file.exists())
        self.assertEqual(self._temp_files(), [])

    def test_saved_todos_can_be_loaded_completely(self) -> None:
        todos = [_todo(1, "第一项"), _todo(2, "第二项")]

        storage.save_todos(todos)

        self.assertEqual(storage.load_todos(), todos)

    def test_normalized_duplicate_ids_keep_all_tasks_and_only_change_conflicting_ids(self) -> None:
        original = [
            {**_todo(1, f"任务 {index}"), "id": raw_id}
            for index, raw_id in enumerate((1, "1", 1.0, "1.0", 2, "2"))
        ]
        self._write_json(self.data_file, original)
        original_bytes = self.data_file.read_bytes()

        loaded = storage.load_todos()

        self.assertEqual(len(loaded), len(original))
        ids = [todo["id"] for todo in loaded]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(all(isinstance(todo_id, int) for todo_id in ids))
        self.assertEqual(ids[0], 1)
        self.assertEqual(ids[4], 2)
        for before, after in zip(original, loaded):
            self.assertEqual(
                {key: value for key, value in before.items() if key != "id"},
                {key: value for key, value in after.items() if key != "id"},
            )
        self.assertEqual(self.data_file.read_bytes(), original_bytes)
        self.assertFalse(self.backup_file.exists())

    def test_repaired_ids_stay_unique_when_generation_collides_with_later_input(self) -> None:
        now = datetime(2026, 9, 5, tzinfo=timezone.utc)
        candidate = int(now.timestamp() * 1000)
        original = [
            _todo(1, "保留第一项"),
            _todo(1, "需要新 ID"),
            _todo(candidate + 1, "与刚生成的 ID 碰撞"),
            {**_todo(0, "非法 ID"), "id": "invalid"},
            {key: value for key, value in _todo(0, "缺失 ID").items() if key != "id"},
        ]
        self._write_json(self.data_file, original)
        with patch("todo_app.storage.datetime") as clock:
            clock.now.return_value = now
            loaded = storage.load_todos()

        ids = [todo["id"] for todo in loaded]
        self.assertEqual(len(loaded), len(original))
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(ids[0], 1)
        self.assertEqual([todo["text"] for todo in loaded], [todo["text"] for todo in original])

    def test_repaired_ids_survive_save_reload_and_original_is_backed_up(self) -> None:
        original = [_todo(1, "第一项"), {**_todo(1, "第二项"), "id": "1"}]
        self._write_json(self.data_file, original)
        original_bytes = self.data_file.read_bytes()
        loaded = storage.load_todos()
        self.assertEqual(len({todo["id"] for todo in loaded}), 2)

        storage.save_todos(loaded)

        self.assertEqual(storage.load_todos(), loaded)
        self.assertEqual(self.backup_file.read_bytes(), original_bytes)
        self.assertEqual(self._temp_files(), [])

    def test_backup_duplicate_ids_are_repaired_without_overwriting_damaged_main(self) -> None:
        damaged = b'{"unfinished":'
        self.data_file.write_bytes(damaged)
        self._write_json(self.backup_file, [_todo(1, "第一项"), _todo(1, "第二项")])
        backup_bytes = self.backup_file.read_bytes()

        with self.assertLogs("todo_app.storage", level="WARNING"):
            loaded = storage.load_todos()

        self.assertEqual(len(loaded), 2)
        self.assertEqual(len({todo["id"] for todo in loaded}), 2)
        with self.assertLogs("todo_app.storage", level="ERROR"):
            storage.save_todos(loaded)
        self.assertEqual(self.data_file.read_bytes(), damaged)
        self.assertEqual(self.backup_file.read_bytes(), backup_bytes)

    def test_window_loads_duplicate_ids_and_completes_only_the_requested_task(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        from todo_app.fonts import apply_application_font
        from todo_app.main_window import ModernTodoAppWindow

        self._write_json(
            self.data_file, [_todo(1, "第一项"), {**_todo(1, "第二项"), "id": "1"}]
        )
        app = QApplication.instance() or QApplication([])
        apply_application_font()
        with patch("todo_app.main_window.QSettings", return_value=MagicMock()):
            window = ModernTodoAppWindow()
        window.master_timer.stop()
        try:
            self.assertEqual(window.list_widget.count(), 2)
            ids = [todo["id"] for todo in window.todos]
            self.assertEqual(set(window._todo_items_by_id), set(ids))
            first_card = window._todo_widgets_by_id[ids[0]]

            window.toggle_complete_todo(ids[1])

            self.assertFalse(window.todos[0]["completed"])
            self.assertTrue(window.todos[1]["completed"])
            self.assertIs(window._todo_widgets_by_id[ids[0]], first_card)
            self.assertEqual(storage.load_todos(), window.todos)
        finally:
            window._quitting_app = True
            window.tray_icon.hide()
            window.close()
            app.processEvents()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()

    def test_existing_valid_main_file_is_preserved_as_backup(self) -> None:
        original = [_todo(1, "旧任务")]
        replacement = [_todo(2, "新任务")]
        self._write_json(self.data_file, original)

        storage.save_todos(replacement)

        self.assertEqual(json.loads(self.data_file.read_text(encoding="utf-8")), replacement)
        self.assertEqual(json.loads(self.backup_file.read_text(encoding="utf-8")), original)
        self.assertEqual(self._temp_files(), [])

    def test_truncated_main_file_recovers_from_backup_without_modifying_main(self) -> None:
        recovered = [_todo(1, "从备份恢复")]
        damaged_content = '[{"id": 1, "text": "截断'
        self.data_file.write_text(damaged_content, encoding="utf-8")
        self._write_json(self.backup_file, recovered)

        with self.assertLogs("todo_app.storage", level="WARNING"):
            loaded = storage.load_todos()

        self.assertEqual(loaded, recovered)
        self.assertEqual(self.data_file.read_text(encoding="utf-8"), damaged_content)

    def test_non_list_main_file_recovers_from_backup(self) -> None:
        recovered = [_todo(1, "结构恢复")]
        self._write_json(self.backup_file, recovered)

        for invalid_top_level in ({"todos": recovered}, "不是列表"):
            with self.subTest(invalid_top_level=invalid_top_level):
                self._write_json(self.data_file, invalid_top_level)
                with self.assertLogs("todo_app.storage", level="WARNING"):
                    loaded = storage.load_todos()
                self.assertEqual(loaded, recovered)
                self.assertEqual(
                    json.loads(self.data_file.read_text(encoding="utf-8")),
                    invalid_top_level,
                )

    def test_damaged_main_and_backup_return_empty_list(self) -> None:
        self.data_file.write_text("{invalid", encoding="utf-8")
        self.backup_file.write_text("[invalid", encoding="utf-8")

        with self.assertLogs("todo_app.storage", level="WARNING"):
            loaded = storage.load_todos()

        self.assertEqual(loaded, [])

    def test_missing_main_file_returns_empty_list_even_when_backup_exists(self) -> None:
        self._write_json(self.backup_file, [_todo(1, "孤立备份")])

        self.assertEqual(storage.load_todos(), [])

    def test_failed_main_replace_keeps_original_and_cleans_temporary_files(self) -> None:
        original = [_todo(1, "原任务")]
        replacement = [_todo(2, "新任务")]
        self._write_json(self.data_file, original)
        real_replace = os.replace

        def fail_main_replace(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            if Path(destination) == self.data_file:
                raise OSError("模拟主文件替换失败")
            real_replace(source, destination)

        with (
            patch("todo_app.storage.os.replace", side_effect=fail_main_replace),
            self.assertLogs("todo_app.storage", level="ERROR"),
        ):
            storage.save_todos(replacement)

        self.assertEqual(json.loads(self.data_file.read_text(encoding="utf-8")), original)
        self.assertEqual(json.loads(self.backup_file.read_text(encoding="utf-8")), original)
        self.assertEqual(self._temp_files(), [])

    def test_fsync_failure_keeps_original_and_cleans_temporary_files(self) -> None:
        original = [_todo(1, "原任务")]
        self._write_json(self.data_file, original)

        with (
            patch("todo_app.storage.os.fsync", side_effect=OSError("模拟 fsync 失败")),
            self.assertLogs("todo_app.storage", level="ERROR"),
        ):
            storage.save_todos([_todo(2, "不会落盘")])

        self.assertEqual(json.loads(self.data_file.read_text(encoding="utf-8")), original)
        self.assertFalse(self.backup_file.exists())
        self.assertEqual(self._temp_files(), [])

    def test_save_refuses_to_overwrite_damaged_main_file(self) -> None:
        damaged_content = '{"unfinished":'
        self.data_file.write_text(damaged_content, encoding="utf-8")

        with self.assertLogs("todo_app.storage", level="ERROR"):
            storage.save_todos([_todo(1, "不会覆盖损坏文件")])

        self.assertEqual(self.data_file.read_text(encoding="utf-8"), damaged_content)
        self.assertFalse(self.backup_file.exists())
        self.assertEqual(self._temp_files(), [])


if __name__ == "__main__":
    unittest.main()
