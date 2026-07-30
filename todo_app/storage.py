"""数据存储与迁移逻辑。"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import REMINDER_SECONDS_TO_TEXT_MAP
from .paths import DATA_FILE


logger = logging.getLogger(__name__)


class _InvalidTodoFile(ValueError):
    """待办文件可读取，但不符合当前顶层结构约束。"""


def _backup_path(data_file: Path) -> Path:
    return data_file.with_name(f"{data_file.name}.bak")


def _decode_todo_list(raw_data: bytes, source: Path) -> list[Any]:
    parsed = json.loads(raw_data.decode("utf-8"))
    if not isinstance(parsed, list):
        raise _InvalidTodoFile(
            f"{source} 顶层类型为 {type(parsed).__name__}，预期为 list"
        )
    return parsed


def _read_todo_list(source: Path) -> list[Any]:
    return _decode_todo_list(source.read_bytes(), source)


def _write_fsynced_temp(destination: Path, content: bytes) -> Path:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as fp:
            temp_path = Path(fp.name)
            fp.write(content)
            fp.flush()
            os.fsync(fp.fileno())
        return temp_path
    except Exception:
        _cleanup_temp(temp_path)
        raise


def _cleanup_temp(temp_path: Path | None) -> None:
    if temp_path is None:
        return
    try:
        temp_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("清理临时数据文件失败: %s", temp_path)


def _migrate_and_validate_todo_item(todo_dict: dict[str, Any], current_index: int, processed: list[dict[str, Any]]
                                    ) -> dict[str, Any]:
    item = dict(todo_dict)
    is_new_id_needed = False
    original_id_for_warning = item.get("id", "未提供")

    if "id" not in item:
        is_new_id_needed = True
    elif not isinstance(item.get("id"), (int, float)):
        try:
            item["id"] = int(float(str(item["id"])))
        except (ValueError, TypeError):
            logger.warning(
                "任务 %r 的 ID %r 无效，将重新生成",
                item.get("text", "未知"),
                original_id_for_warning,
            )
            is_new_id_needed = True
    elif isinstance(item.get("id"), float):
        item["id"] = int(item["id"])

    if is_new_id_needed:
        processed_ids = [it["id"] for it in processed if isinstance(it.get("id"), int)]
        current_max_id = max(processed_ids) if processed_ids else 0
        candidate_id = int(datetime.now(timezone.utc).timestamp() * 1000) + current_index
        new_id = max(candidate_id, current_max_id + 1 if processed_ids else candidate_id)
        existing_ids = set(processed_ids)
        while new_id in existing_ids:
            new_id += 1
        item["id"] = new_id

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
    return item


def load_todos() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []

    source = DATA_FILE
    try:
        todos_from_file = _read_todo_list(DATA_FILE)
    except Exception as exc:  # noqa: BLE001
        backup = _backup_path(DATA_FILE)
        logger.warning(
            "主数据文件 %s 不可用，将尝试只读加载备份 %s；主文件会保持原样: %s",
            DATA_FILE,
            backup,
            exc,
        )
        try:
            todos_from_file = _read_todo_list(backup)
            source = backup
        except Exception as backup_exc:  # noqa: BLE001
            logger.warning(
                "主数据文件与备份均不可用，将返回空列表；主文件会保持原样: %s",
                backup_exc,
            )
            return []

    if source != DATA_FILE:
        logger.warning("已从备份 %s 恢复待办数据，损坏的主文件 %s 未被修改", source, DATA_FILE)

    migrated: list[dict[str, Any]] = []
    for index, todo_data in enumerate(todos_from_file):
        if not isinstance(todo_data, dict):
            logger.warning("文件中发现非字典类型的任务项 %r，已跳过", str(todo_data)[:100])
            continue
        try:
            migrated.append(_migrate_and_validate_todo_item(todo_data, index, migrated))
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "迁移和验证任务 %r 时失败，该任务将被跳过: %s",
                str(todo_data)[:100],
                exc,
            )
    return migrated


def save_todos(todos_list: list[dict[str, Any]]) -> None:
    data_temp: Path | None = None
    backup_temp: Path | None = None
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(todos_list, ensure_ascii=False, indent=4).encode("utf-8")
        data_temp = _write_fsynced_temp(DATA_FILE, serialized)

        if DATA_FILE.exists():
            current_content = DATA_FILE.read_bytes()
            try:
                _decode_todo_list(current_content, DATA_FILE)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "拒绝覆盖不可用的主数据文件 %s；请先人工保留或移走该文件: %s",
                    DATA_FILE,
                    exc,
                )
                return

            backup = _backup_path(DATA_FILE)
            backup_temp = _write_fsynced_temp(backup, current_content)
            os.replace(backup_temp, backup)
            backup_temp = None

        os.replace(data_temp, DATA_FILE)
        data_temp = None
    except Exception as exc:  # noqa: BLE001
        logger.exception("保存数据时出错，原主文件保持不变: %s", exc)
    finally:
        _cleanup_temp(backup_temp)
        _cleanup_temp(data_temp)


__all__ = [
    "load_todos",
    "save_todos",
    "REMINDER_SECONDS_TO_TEXT_MAP",
]
