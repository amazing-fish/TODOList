"""提醒与截止时间策略封装。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass(frozen=True)
class NotificationDecision:
    """描述提醒与到期通知的判定结果。"""

    due_datetime: Optional[datetime]
    should_fire_reminder: bool = False
    should_fire_due: bool = False
    reminder_time: Optional[datetime] = None
    error: Optional[str] = None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """解析 ISO8601 字符串，失败时返回 ``None``。"""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _ensure_utc(parsed)


def normalize_reminder_settings(todo: dict) -> None:
    """
    确保待办的提醒配置与截止时间保持一致。

    - 若未设置截止时间，则强制关闭提醒。
    - 纠正 ``reminderOffset`` 的数值类型。
    """

    try:
        todo["reminderOffset"] = int(todo.get("reminderOffset", -1))
    except (TypeError, ValueError):
        todo["reminderOffset"] = -1

    if not todo.get("dueDate"):
        todo["reminderOffset"] = -1
        todo["snoozeUntil"] = None
        todo["notifiedForReminder"] = False
        todo["notifiedForDue"] = False


def clear_expired_snooze(todo: dict, current_time_utc: datetime) -> bool:
    """
    若推迟时间已过期或非法，则清除并返回 ``True`` 表示发生了更新。
    """

    snooze_until = todo.get("snoozeUntil")
    snooze_dt = parse_iso_datetime(snooze_until)
    if snooze_until and snooze_dt is None:
        todo["snoozeUntil"] = None
        return True
    if snooze_dt and snooze_dt <= current_time_utc:
        todo.update(
            {
                "snoozeUntil": None,
                "notifiedForReminder": False,
                "notifiedForDue": False,
            }
        )
        return True
    return False


def evaluate_notification_decision(todo: dict, current_time_utc: datetime) -> NotificationDecision:
    """计算当前待办是否需要触发提醒或到期通知。"""

    due_dt = parse_iso_datetime(todo.get("dueDate"))
    if todo.get("dueDate") and due_dt is None:
        return NotificationDecision(
            due_datetime=None,
            error=f"错误: 任务ID {todo.get('id', '未知')} 截止日期格式无效: {todo.get('dueDate')}",
        )
    if due_dt is None:
        return NotificationDecision(due_datetime=None)

    snooze_dt = parse_iso_datetime(todo.get("snoozeUntil"))
    if snooze_dt and snooze_dt > current_time_utc:
        return NotificationDecision(due_datetime=due_dt)

    try:
        reminder_offset = int(todo.get("reminderOffset", -1))
    except (TypeError, ValueError):
        reminder_offset = -1

    should_fire_reminder = False
    reminder_time = None
    if (
        reminder_offset >= 0
        and not todo.get("notifiedForReminder", False)
        and not todo.get("completed", False)
    ):
        reminder_time = due_dt - timedelta(seconds=reminder_offset)
        if reminder_time <= current_time_utc < due_dt:
            should_fire_reminder = True

    should_fire_due = (
        due_dt <= current_time_utc
        and not todo.get("notifiedForDue", False)
        and not todo.get("completed", False)
    )

    return NotificationDecision(
        due_datetime=due_dt,
        should_fire_reminder=should_fire_reminder,
        should_fire_due=should_fire_due,
        reminder_time=reminder_time,
    )


__all__ = [
    "NotificationDecision",
    "clear_expired_snooze",
    "evaluate_notification_decision",
    "normalize_reminder_settings",
    "parse_iso_datetime",
]
