"""数据存储与迁移逻辑。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .constants import REMINDER_SECONDS_TO_TEXT_MAP
from .paths import DATA_FILE


def _migrate_and_validate_todo_item(
    todo_dict: dict[str, Any],
    current_index: int,
    _processed: list[dict[str, Any]],
    existing_ids: set[int],
    current_max_id: int,
) -> tuple[dict[str, Any], int]:
    item = dict(todo_dict)
    is_new_id_needed = False
    original_id_for_warning = item.get("id", "未提供")

    if "id" not in item:
        is_new_id_needed = True
    elif not isinstance(item.get("id"), (int, float)):
        try:
            item["id"] = int(float(str(item["id"])))
        except (ValueError, TypeError):
            print(f"警告: 任务 '{item.get('text', '未知')}' 的ID '{original_id_for_warning}' 无效，将重新生成。")
            is_new_id_needed = True
    elif isinstance(item.get("id"), float):
        item["id"] = int(item["id"])

    normalized_id = item.get("id")
    if not is_new_id_needed and isinstance(normalized_id, int):
        if normalized_id in existing_ids:
            is_new_id_needed = True

    if is_new_id_needed:
        candidate_id = int(datetime.now(timezone.utc).timestamp() * 1000) + current_index
        next_available = current_max_id + 1 if existing_ids else candidate_id
        new_id = max(candidate_id, next_available)
        while new_id in existing_ids:
            new_id += 1
        item["id"] = new_id
        normalized_id = new_id

    if isinstance(normalized_id, int):
        existing_ids.add(normalized_id)
        current_max_id = max(current_max_id, normalized_id)

    item.setdefault("createdAt", datetime.now(timezone.utc).isoformat())
    if not item["createdAt"]:
        item["createdAt"] = datetime.now(timezone.utc).isoformat()

    item.setdefault("completed", False)
    item.setdefault("priority", "中")
    item.setdefault("dueDate", None)
    item.setdefault("reminderOffset", 0)
    item.setdefault("snoozeUntil", None)
    item.setdefault("lastNotifiedAt", None)
    item.setdefault("notifiedForReminder", False)
    item.setdefault("notifiedForDue", False)
    return item, current_max_id


def load_todos() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as fp:
            todos_from_file = json.load(fp)
    except json.JSONDecodeError:
        print(f"警告: {DATA_FILE} 文件格式错误或为空，将使用空列表。")
        return []
    except Exception as exc:  # noqa: BLE001
        print(f"加载数据时发生未预料的错误: {exc}")
        return []

    if not isinstance(todos_from_file, list):
        print(f"警告: {DATA_FILE} 内容不是一个列表，将使用空列表。")
        return []

    migrated: list[dict[str, Any]] = []
    existing_ids: set[int] = set()
    current_max_id = 0
    for index, todo_data in enumerate(todos_from_file):
        if not isinstance(todo_data, dict):
            print(f"警告: 文件中发现非字典类型的任务项: {str(todo_data)[:100]}，已跳过。")
            continue
        try:
            migrated_item, current_max_id = _migrate_and_validate_todo_item(
                todo_data,
                index,
                migrated,
                existing_ids,
                current_max_id,
            )
            migrated.append(migrated_item)
        except Exception as exc:  # noqa: BLE001
            print(f"严重错误: 迁移和验证任务 '{str(todo_data)[:100]}' 时失败: {exc}。该任务将被跳过。")
    return migrated


def save_todos(todos_list: list[dict[str, Any]]) -> None:
    try:
        with DATA_FILE.open("w", encoding="utf-8") as fp:
            json.dump(todos_list, fp, ensure_ascii=False, indent=4)
    except Exception as exc:  # noqa: BLE001
        print(f"保存数据时出错: {exc}")


__all__ = [
    "load_todos",
    "save_todos",
    "REMINDER_SECONDS_TO_TEXT_MAP",
]
