"""待办数据原子写入与损坏恢复测试。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
