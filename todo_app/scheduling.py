"""提醒、推迟与编辑时的调度状态规则。"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any

_WEEKDAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


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

    if due_date_dt <= snooze_until_dt:
        updated_fields["dueDate"] = snooze_until_dt.isoformat()
    return updated_fields


def normalize_recurrence(raw: Any) -> dict[str, Any] | None:
    """规范化循环规则；无效或关闭时返回 None，兼容旧版 todos.json。"""

    if not isinstance(raw, dict):
        return None
    frequency = raw.get("frequency")
    if not isinstance(frequency, str):
        return None
    frequency = frequency.strip().lower()

    if frequency == "daily":
        interval_raw = raw.get("interval", 1)
        try:
            interval = int(interval_raw)
        except (TypeError, ValueError):
            interval = 1
        interval = max(1, min(interval, 365))
        return {
            "frequency": "daily",
            "interval": interval,
            "skipWeekends": bool(raw.get("skipWeekends", False)),
        }

    if frequency == "weekdays":
        return {"frequency": "weekdays"}

    if frequency == "weekly":
        raw_days = raw.get("weekdays")
        days: list[int] = []
        if isinstance(raw_days, (list, tuple, set)):
            seen: set[int] = set()
            for item in raw_days:
                try:
                    day_idx = int(item)
                except (TypeError, ValueError):
                    continue
                if 0 <= day_idx <= 6 and day_idx not in seen:
                    seen.add(day_idx)
                    days.append(day_idx)
        days.sort()
        return {"frequency": "weekly", "weekdays": days}

    if frequency == "monthly":
        day_raw = raw.get("day", 1)
        try:
            day = int(day_raw)
        except (TypeError, ValueError):
            day = 1
        day = max(1, min(day, 31))
        return {"frequency": "monthly", "day": day}

    if frequency == "yearly":
        try:
            month = int(raw.get("month", 1))
        except (TypeError, ValueError):
            month = 1
        try:
            day = int(raw.get("day", 1))
        except (TypeError, ValueError):
            day = 1
        month = max(1, min(month, 12))
        max_feb_or_month = 29 if month == 2 else calendar.monthrange(2024, month)[1]
        day = max(1, min(day, max_feb_or_month))
        return {"frequency": "yearly", "month": month, "day": day}

    return None


def format_recurrence_label(recurrence: Any) -> str:
    """将规范化循环规则格式化为紧凑的中文标签。"""

    rule = normalize_recurrence(recurrence)
    if rule is None:
        return ""
    freq = rule["frequency"]
    if freq == "daily":
        interval = rule["interval"]
        base = "每天" if interval == 1 else f"每{interval}天"
        if rule.get("skipWeekends"):
            return f"{base}(工作日)"
        return base
    if freq == "weekdays":
        return "工作日"
    if freq == "weekly":
        days = rule.get("weekdays") or []
        if not days:
            return "每周"
        return "每" + "/".join(_WEEKDAY_LABELS[d] for d in days)
    if freq == "monthly":
        return f"每月{rule['day']}日"
    if freq == "yearly":
        return f"每年{rule['month']}月{rule['day']}日"
    return ""


def _add_months_clamped(anchor_date: date, months_delta: int, anchor_day: int) -> date:
    total_months = (anchor_date.year * 12 + (anchor_date.month - 1)) + months_delta
    target_year = total_months // 12
    target_month = (total_months % 12) + 1
    max_day = calendar.monthrange(target_year, target_month)[1]
    return date(target_year, target_month, min(anchor_day, max_day))


def _combine_local(target_date: date, template_local: datetime) -> datetime:
    naive = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        template_local.hour,
        template_local.minute,
        template_local.second,
        template_local.microsecond,
    )
    if template_local.tzinfo is None:
        return naive.replace(tzinfo=timezone.utc)
    return naive.replace(tzinfo=template_local.tzinfo)


def _advance_once_local(current_local: datetime, rule: dict[str, Any]) -> datetime:
    freq = rule["frequency"]
    current_date = current_local.date()

    if freq == "daily":
        interval = int(rule.get("interval", 1))
        next_date = current_date + timedelta(days=interval)
        if rule.get("skipWeekends"):
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)
        return _combine_local(next_date, current_local)

    if freq == "weekdays":
        next_date = current_date + timedelta(days=1)
        while next_date.weekday() >= 5:
            next_date += timedelta(days=1)
        return _combine_local(next_date, current_local)

    if freq == "weekly":
        allowed = rule.get("weekdays") or [current_date.weekday()]
        next_date = current_date + timedelta(days=1)
        while next_date.weekday() not in allowed:
            next_date += timedelta(days=1)
        return _combine_local(next_date, current_local)

    if freq == "monthly":
        anchor_day = int(rule.get("day", current_date.day))
        next_date = _add_months_clamped(current_date, 1, anchor_day)
        return _combine_local(next_date, current_local)

    if freq == "yearly":
        anchor_month = int(rule.get("month", current_date.month))
        anchor_day = int(rule.get("day", current_date.day))
        next_year = current_date.year + 1
        max_day = calendar.monthrange(next_year, anchor_month)[1]
        next_date = date(next_year, anchor_month, min(anchor_day, max_day))
        return _combine_local(next_date, current_local)

    return current_local + timedelta(days=1)


def calculate_next_due_utc(
    due_date_iso: str,
    recurrence: Any,
    *,
    reference_utc: datetime,
    target_tz: tzinfo | None = None,
) -> str:
    """计算下一次周期截止时间（UTC ISO），离线错过多期时快进至下一未来周期。"""

    rule = normalize_recurrence(recurrence)
    if rule is None:
        raise ValueError("循环规则无效")

    if reference_utc.tzinfo is None:
        ref_utc = reference_utc.replace(tzinfo=timezone.utc)
    else:
        ref_utc = reference_utc.astimezone(timezone.utc)

    due_utc = _parse_utc_datetime(due_date_iso) or ref_utc
    resolved_tz = target_tz if target_tz is not None else datetime.now().astimezone().tzinfo
    if resolved_tz is None:
        resolved_tz = timezone.utc

    candidate_local = due_utc.astimezone(resolved_tz)

    # 针对多天离线快速跳跃，避免极端间隔逐天循环
    if rule["frequency"] == "daily" and not rule.get("skipWeekends"):
        interval = int(rule["interval"])
        if candidate_local.astimezone(timezone.utc) <= ref_utc:
            days_gap = max((ref_utc.astimezone(resolved_tz).date() - candidate_local.date()).days, 0)
            steps = days_gap // interval
            if steps > 1:
                jumped_date = candidate_local.date() + timedelta(days=(steps - 1) * interval)
                candidate_local = _combine_local(jumped_date, candidate_local)
    elif rule["frequency"] == "yearly":
        ref_year = ref_utc.astimezone(resolved_tz).year
        if ref_year - candidate_local.year > 1:
            jumped_year = ref_year - 1
            m = int(rule["month"])
            d = min(int(rule["day"]), calendar.monthrange(jumped_year, m)[1])
            candidate_local = _combine_local(date(jumped_year, m, d), candidate_local)
    elif rule["frequency"] == "monthly":
        ref_local_date = ref_utc.astimezone(resolved_tz).date()
        months_gap = (ref_local_date.year - candidate_local.year) * 12 + (
            ref_local_date.month - candidate_local.month
        )
        if months_gap > 1:
            jumped_date = _add_months_clamped(
                candidate_local.date(), months_gap - 1, int(rule["day"])
            )
            candidate_local = _combine_local(jumped_date, candidate_local)

    for _ in range(1024):
        candidate_local = _advance_once_local(candidate_local, rule)
        if candidate_local.astimezone(timezone.utc) > ref_utc:
            break

    return candidate_local.astimezone(timezone.utc).isoformat()


def build_recurrence_completion_fields(
    todo: dict[str, Any],
    *,
    now_utc: datetime | None = None,
    target_tz: tzinfo | None = None,
) -> dict[str, Any] | None:
    """对循环任务执行“完成即顺延”，非循环或无截止返回 None。"""

    rule = normalize_recurrence(todo.get("recurrence"))
    due_date = todo.get("dueDate")
    if rule is None or not due_date:
        return None

    ref = now_utc or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    else:
        ref = ref.astimezone(timezone.utc)

    next_due_iso = calculate_next_due_utc(
        str(due_date),
        rule,
        reference_utc=ref,
        target_tz=target_tz,
    )
    return {
        "completed": False,
        "dueDate": next_due_iso,
        "snoozeUntil": None,
        "notifiedForReminder": False,
        "notifiedForDue": False,
        "lastNotifiedAt": None,
    }


def build_edit_update_fields(existing: dict[str, Any], updated_data: dict[str, Any]) -> dict[str, Any]:
    """生成编辑保存字段，仅在调度设置变化时重置提醒状态。"""

    due_date_changed = not _due_dates_are_equivalent(
        existing.get("dueDate"),
        updated_data["dueDate"],
    )
    resolved_due = updated_data["dueDate"] if due_date_changed else existing.get("dueDate")
    resolved_recurrence = (
        normalize_recurrence(updated_data.get("recurrence"))
        if resolved_due is not None and "recurrence" in updated_data
        else (None if resolved_due is None else normalize_recurrence(existing.get("recurrence")))
    )

    updated_fields: dict[str, Any] = {
        "text": updated_data["text"],
        "priority": updated_data["priority"],
        "dueDate": resolved_due,
        "reminderOffset": updated_data["reminderOffset"],
        "recurrence": resolved_recurrence,
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
    "build_recurrence_completion_fields",
    "build_snooze_update_fields",
    "calculate_next_due_utc",
    "format_recurrence_label",
    "normalize_recurrence",
]
