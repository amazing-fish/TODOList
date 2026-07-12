"""提醒、推迟与编辑时的调度状态规则。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _parse_utc_datetime(value: object) -> datetime | None:
    """解析 ISO 时间，并统一为 UTC aware datetime。"""

    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _due_dates_are_equivalent(existing_value: object, updated_value: object) -> bool:
    """按 Qt 可表达的毫秒精度比较两个截止时间是否为同一时刻。"""

    if existing_value == updated_value:
        return True

    existing_dt = _parse_utc_datetime(existing_value)
    updated_dt = _parse_utc_datetime(updated_value)
    if existing_dt is None or updated_dt is None:
        return False

    existing_ms = existing_dt.replace(microsecond=(existing_dt.microsecond // 1000) * 1000)
    updated_ms = updated_dt.replace(microsecond=(updated_dt.microsecond // 1000) * 1000)
    return existing_ms == updated_ms


def build_snooze_update_fields(
    todo: dict[str, Any],
    snooze_duration: timedelta,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """生成推迟后的任务字段，保证编辑默认时间跟随推迟结果。"""

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    snooze_until_dt = now_utc + snooze_duration
    updated_fields: dict[str, Any] = {
        "snoozeUntil": snooze_until_dt.isoformat(),
        "notifiedForReminder": False,
        "notifiedForDue": False,
        "lastNotifiedAt": None,
    }

    due_date_dt = _parse_utc_datetime(todo.get("dueDate"))
    if due_date_dt is None:
        if todo.get("dueDate"):
            updated_fields["dueDate"] = snooze_until_dt.isoformat()
        return updated_fields

    shifted_due_dt = due_date_dt + snooze_duration
    if shifted_due_dt < snooze_until_dt:
        shifted_due_dt = snooze_until_dt
    updated_fields["dueDate"] = shifted_due_dt.isoformat()
    return updated_fields


def build_edit_update_fields(existing: dict[str, Any], updated_data: dict[str, Any]) -> dict[str, Any]:
    """生成编辑保存字段，仅在调度设置变化时重置提醒状态。"""

    due_date_changed = not _due_dates_are_equivalent(
        existing.get("dueDate"),
        updated_data["dueDate"],
    )

    updated_fields: dict[str, Any] = {
        "text": updated_data["text"],
        "priority": updated_data["priority"],
        "dueDate": updated_data["dueDate"] if due_date_changed else existing.get("dueDate"),
        "reminderOffset": updated_data["reminderOffset"],
    }

    schedule_changed = (
        due_date_changed or existing.get("reminderOffset", 0) != updated_data["reminderOffset"]
    )
    if schedule_changed:
        updated_fields.update(
            {
                "snoozeUntil": None,
                "notifiedForReminder": False,
                "notifiedForDue": False,
                "lastNotifiedAt": None,
            }
        )

    return updated_fields


__all__ = [
    "build_edit_update_fields",
    "build_snooze_update_fields",
]
