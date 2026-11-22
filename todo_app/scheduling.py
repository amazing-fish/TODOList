"""提醒、推迟与编辑时的调度状态规则。"""
from __future__ import annotations

import calendar
import math
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any

_WEEKDAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _safe_int(value: Any, default: int) -> int:
    """安全转换整数配置，拒收布尔与 Infinity/NaN 等非有限浮点。"""

    if isinstance(value, bool):
        return default
    if isinstance(value, float) and not math.isfinite(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _parse_utc_datetime(value: object) -> datetime | None:
    """解析 ISO 时间，并统一为 UTC aware datetime。"""

    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    try:
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except OverflowError:
        return None


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


def _normalize_anchor_time(raw_value: object) -> str | None:
    """规范化本地墙钟锚点时间（HH:MM / HH:MM:SS / HH:MM:SS.ffffff），拒收带偏移/无效串。"""

    if not isinstance(raw_value, str):
        return None
    cleaned = raw_value.strip()
    if not cleaned or any(marker in cleaned for marker in ("T", "t", "Z", "z", "+", "-", " ")):
        return None
    try:
        parsed = time.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return None
    if parsed.microsecond:
        return parsed.isoformat()
    if parsed.second:
        return parsed.strftime("%H:%M:%S")
    return parsed.strftime("%H:%M")


def _format_local_anchor_time(local_dt: datetime) -> str:
    if local_dt.microsecond:
        return time(
            local_dt.hour,
            local_dt.minute,
            local_dt.second,
            local_dt.microsecond,
        ).isoformat()
    if local_dt.second:
        return local_dt.strftime("%H:%M:%S")
    return local_dt.strftime("%H:%M")


def normalize_recurrence(raw: Any) -> dict[str, Any] | None:
    """规范化循环规则；无效或关闭时返回 None，兼容旧版 todos.json。"""

    if not isinstance(raw, dict):
        return None
    frequency = raw.get("frequency")
    if not isinstance(frequency, str):
        return None
    frequency = frequency.strip().lower()
    anchor_time = _normalize_anchor_time(raw.get("anchorTime"))

    normalized: dict[str, Any] | None = None
    if frequency == "daily":
        interval = max(1, min(_safe_int(raw.get("interval", 1), 1), 365))
        normalized = {
            "frequency": "daily",
            "interval": interval,
            "skipWeekends": bool(raw.get("skipWeekends", False)),
        }
    elif frequency == "weekdays":
        normalized = {"frequency": "weekdays"}
    elif frequency == "weekly":
        raw_days = raw.get("weekdays")
        days: list[int] = []
        if isinstance(raw_days, (list, tuple, set)):
            seen: set[int] = set()
            for item in raw_days:
                day_idx = _safe_int(item, -1)
                if 0 <= day_idx <= 6 and day_idx not in seen:
                    seen.add(day_idx)
                    days.append(day_idx)
        days.sort()
        normalized = {"frequency": "weekly", "weekdays": days}
    elif frequency == "monthly":
        day = max(1, min(_safe_int(raw.get("day", 1), 1), 31))
        normalized = {"frequency": "monthly", "day": day}
    elif frequency == "yearly":
        month = max(1, min(_safe_int(raw.get("month", 1), 1), 12))
        day_raw = _safe_int(raw.get("day", 1), 1)
        max_feb_or_month = 29 if month == 2 else calendar.monthrange(2024, month)[1]
        day = max(1, min(day_raw, max_feb_or_month))
        normalized = {"frequency": "yearly", "month": month, "day": day}

    if normalized is not None and anchor_time is not None:
        normalized["anchorTime"] = anchor_time
    return normalized


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


def _combine_local(
    target_date: date,
    template_local: datetime,
    *,
    resolve_system_dst: bool = False,
) -> datetime:
    naive = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        template_local.hour,
        template_local.minute,
        template_local.second,
        template_local.microsecond,
    )
    if resolve_system_dst:
        return naive.astimezone()
    if template_local.tzinfo is None:
        return naive.replace(tzinfo=timezone.utc)
    return naive.replace(tzinfo=template_local.tzinfo)


def _advance_date_once(current_date: date, rule: dict[str, Any]) -> date:
    freq = rule["frequency"]

    if freq == "daily":
        interval = int(rule.get("interval", 1))
        next_date = current_date + timedelta(days=interval)
        if rule.get("skipWeekends"):
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)
        return next_date

    if freq == "weekdays":
        next_date = current_date + timedelta(days=1)
        while next_date.weekday() >= 5:
            next_date += timedelta(days=1)
        return next_date

    if freq == "weekly":
        allowed = rule.get("weekdays") or [current_date.weekday()]
        next_date = current_date + timedelta(days=1)
        while next_date.weekday() not in allowed:
            next_date += timedelta(days=1)
        return next_date

    if freq == "monthly":
        anchor_day = int(rule.get("day", current_date.day))
        return _add_months_clamped(current_date, 1, anchor_day)

    if freq == "yearly":
        anchor_month = int(rule.get("month", current_date.month))
        anchor_day = int(rule.get("day", current_date.day))
        next_year = current_date.year + 1
        max_day = calendar.monthrange(next_year, anchor_month)[1]
        return date(next_year, anchor_month, min(anchor_day, max_day))

    return current_date + timedelta(days=1)


def _advance_once_local(
    current_local: datetime,
    rule: dict[str, Any],
    *,
    resolve_system_dst: bool = False,
) -> datetime:
    next_date = _advance_date_once(current_local.date(), rule)
    return _combine_local(
        next_date, current_local, resolve_system_dst=resolve_system_dst
    )


def calculate_next_due_utc(
    due_date_iso: str,
    recurrence: Any,
    *,
    reference_utc: datetime,
    target_tz: tzinfo | None = None,
) -> str:
    """计算下一次周期截止时间（UTC ISO），保持原始本地墙钟时间锚点不因 DST 空洞漂移。"""

    rule = normalize_recurrence(recurrence)
    if rule is None:
        raise ValueError("循环规则无效")

    if reference_utc.tzinfo is None:
        ref_utc = reference_utc.replace(tzinfo=timezone.utc)
    else:
        ref_utc = reference_utc.astimezone(timezone.utc)

    due_utc = _parse_utc_datetime(due_date_iso) or ref_utc
    resolve_system_dst = target_tz is None
    if resolve_system_dst:
        anchor_local = due_utc.astimezone()
        ref_local_date = ref_utc.astimezone().date()
    else:
        anchor_local = due_utc.astimezone(target_tz)
        ref_local_date = ref_utc.astimezone(target_tz).date()

    candidate_date = anchor_local.date()
    anchor_template = anchor_local
    anchor_time_str = rule.get("anchorTime")
    if isinstance(anchor_time_str, str):
        parsed_anchor_time = time.fromisoformat(anchor_time_str)
        anchor_template = anchor_local.replace(
            hour=parsed_anchor_time.hour,
            minute=parsed_anchor_time.minute,
            second=parsed_anchor_time.second,
            microsecond=parsed_anchor_time.microsecond,
        )

    def _to_utc(target_date: date) -> datetime:
        return _combine_local(
            target_date, anchor_template, resolve_system_dst=resolve_system_dst
        ).astimezone(timezone.utc)

    # 针对多天/多年离线快速跳跃；始终基于原始墙钟时间锚点解析，避免 DST 空洞漂移
    if rule["frequency"] == "daily" and not rule.get("skipWeekends"):
        interval = int(rule["interval"])
        if _to_utc(candidate_date) <= ref_utc:
            days_gap = max((ref_local_date - candidate_date).days, 0)
            steps = days_gap // interval
            if steps > 1:
                candidate_date = candidate_date + timedelta(days=(steps - 1) * interval)
    elif rule["frequency"] == "daily" and rule.get("skipWeekends") and int(rule["interval"]) > 1:
        if _to_utc(candidate_date) <= ref_utc and ref_local_date > candidate_date:
            seen_weekdays: dict[int, date] = {candidate_date.weekday(): candidate_date}
            probe_date = candidate_date
            for _ in range(10):
                next_probe = _advance_date_once(probe_date, rule)
                if _to_utc(next_probe) > ref_utc:
                    candidate_date = probe_date
                    break
                probe_date = next_probe
                wd = probe_date.weekday()
                if wd in seen_weekdays:
                    cycle_days = (probe_date - seen_weekdays[wd]).days
                    remaining_days = (ref_local_date - probe_date).days - 7
                    if cycle_days > 0 and remaining_days > cycle_days:
                        cycles = remaining_days // cycle_days
                        candidate_date = probe_date + timedelta(days=cycles * cycle_days)
                    else:
                        candidate_date = probe_date
                    break
                seen_weekdays[wd] = probe_date
                candidate_date = probe_date
    elif rule["frequency"] in ("weekdays", "weekly") or (
        rule["frequency"] == "daily" and rule.get("skipWeekends") and int(rule["interval"]) == 1
    ):
        if _to_utc(candidate_date) <= ref_utc:
            days_gap = max((ref_local_date - candidate_date).days, 0)
            weeks = days_gap // 7
            if weeks > 1:
                candidate_date = candidate_date + timedelta(days=(weeks - 1) * 7)
    elif rule["frequency"] == "yearly":
        if ref_local_date.year - candidate_date.year > 1:
            jumped_year = ref_local_date.year - 1
            m = int(rule["month"])
            d = min(int(rule["day"]), calendar.monthrange(jumped_year, m)[1])
            candidate_date = date(jumped_year, m, d)
    elif rule["frequency"] == "monthly":
        months_gap = (ref_local_date.year - candidate_date.year) * 12 + (
            ref_local_date.month - candidate_date.month
        )
        if months_gap > 1:
            candidate_date = _add_months_clamped(
                candidate_date, months_gap - 1, int(rule["day"])
            )

    candidate_utc = _to_utc(candidate_date)
    for _ in range(4096):
        candidate_date = _advance_date_once(candidate_date, rule)
        candidate_utc = _to_utc(candidate_date)
        if candidate_utc > ref_utc:
            break

    if candidate_utc <= ref_utc:
        raise ValueError("无法将循环任务推进至晚于当前时刻的下一次截止时间")
    return candidate_utc.isoformat()


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
    updated_rule = dict(rule)
    if "anchorTime" not in updated_rule:
        due_utc = _parse_utc_datetime(due_date)
        if due_utc is not None:
            source_local = due_utc.astimezone() if target_tz is None else due_utc.astimezone(target_tz)
            updated_rule["anchorTime"] = _format_local_anchor_time(source_local)
    return {
        "completed": False,
        "dueDate": next_due_iso,
        "recurrence": updated_rule,
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
    if due_date_changed and resolved_recurrence is not None and "anchorTime" in resolved_recurrence:
        updated_rule = updated_data.get("recurrence") if "recurrence" in updated_data else None
        explicit_anchor = (
            _normalize_anchor_time(updated_rule.get("anchorTime"))
            if isinstance(updated_rule, dict)
            else None
        )
        if explicit_anchor is None:
            resolved_recurrence.pop("anchorTime", None)

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
