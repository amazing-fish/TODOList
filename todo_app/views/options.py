"""待办列表的筛选与排序配置。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


Predicate = Callable[[dict], bool]
SortKey = Callable[[dict], object]


@dataclass(frozen=True)
class FilterOption:
    """筛选配置项。"""

    label: str
    predicate: Predicate


@dataclass(frozen=True)
class SortOption:
    """排序配置项。"""

    label: str
    key: SortKey
    reverse: bool = False


def _is_completed(todo: dict) -> bool:
    return bool(todo.get("completed", False))


def _parse_iso_datetime(raw_value: object) -> datetime | None:
    if not raw_value:
        return None
    if not isinstance(raw_value, str):
        try:
            raw_value = str(raw_value)
        except Exception:  # noqa: BLE001
            return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _due_date_key(todo: dict, *, future_extreme: bool = True) -> datetime:
    parsed = _parse_iso_datetime(todo.get("dueDate"))
    if parsed is not None:
        return parsed
    extreme = datetime.max if future_extreme else datetime.min
    return extreme.replace(tzinfo=timezone.utc)


def _created_at_key(todo: dict) -> datetime:
    parsed = _parse_iso_datetime(todo.get("createdAt"))
    if parsed is not None:
        return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def _priority_rank(todo: dict) -> int:
    priority = todo.get("priority")
    mapping = {"高": 0, "中": 1, "低": 2}
    return mapping.get(priority, 3)


def _filter_all(_: dict) -> bool:
    return True


def _filter_pending(todo: dict) -> bool:
    return not _is_completed(todo)


def _filter_completed(todo: dict) -> bool:
    return _is_completed(todo)


def _filter_due_today(todo: dict) -> bool:
    if _is_completed(todo):
        return False
    parsed = _parse_iso_datetime(todo.get("dueDate"))
    if parsed is None:
        return False
    try:
        return parsed.astimezone().date() == datetime.now().astimezone().date()
    except ValueError:
        return False


def _filter_high_priority(todo: dict) -> bool:
    return (not _is_completed(todo)) and todo.get("priority") == "高"


FILTER_OPTIONS: tuple[FilterOption, ...] = (
    FilterOption("全部", _filter_all),
    FilterOption("未完成", _filter_pending),
    FilterOption("已完成", _filter_completed),
    FilterOption("今天到期", _filter_due_today),
    FilterOption("高优先级", _filter_high_priority),
)


FILTER_OPTION_MAP = {option.label: option for option in FILTER_OPTIONS}


SORT_OPTIONS: tuple[SortOption, ...] = (
    SortOption("创建时间 (新->旧)", _created_at_key, True),
    SortOption("创建时间 (旧->新)", _created_at_key, False),
    SortOption(
        "截止日期 (近->远)",
        lambda todo: (_is_completed(todo), _due_date_key(todo, future_extreme=True)),
    ),
    SortOption(
        "截止日期 (远->近)",
        lambda todo: (_is_completed(todo), _due_date_key(todo, future_extreme=True)),
        True,
    ),
    SortOption(
        "优先级 (高->低)",
        lambda todo: (
            _is_completed(todo),
            _priority_rank(todo),
            _due_date_key(todo, future_extreme=True),
        ),
    ),
)


SORT_OPTION_MAP = {option.label: option for option in SORT_OPTIONS}


__all__ = [
    "FilterOption",
    "SortOption",
    "FILTER_OPTIONS",
    "SORT_OPTIONS",
    "FILTER_OPTION_MAP",
    "SORT_OPTION_MAP",
]
