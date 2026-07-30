"""任务卡片的纯尺寸分配规则。

Qt 边界负责提供字体、样式和屏幕几何的测量值；本模块只处理普通 Python
数值，不创建控件，也不依赖事件循环。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class TaskCardLayoutInput:
    """计算任务卡片所需的已测量值与现有布局参数。"""

    viewport_width: int
    list_spacing: int
    card_frame_horizontal_inset: int
    card_frame_vertical_inset: int
    main_layout_spacing: int
    main_layout_vertical_inset: int
    complete_area_width: int
    complete_area_height: int
    task_natural_width: int
    priority_natural_width: int
    task_area_floor_width: int
    task_area_maximum_minimum_width: int
    task_text_horizontal_inset: int
    task_text_vertical_inset: int
    logical_line_count: int
    line_height: int
    content_layout_vertical_inset: int
    content_layout_spacing: int
    priority_height: int
    timer_natural_width: int
    timer_base_minimum_width: int
    timer_prefix_minimum_width: int
    timer_text_horizontal_inset: int
    timer_height: int
    action_area_width: int
    card_minimum_height: int


@dataclass(frozen=True)
class TaskCardLayout:
    """任务卡片各区域的最终宽高决策。"""

    card_width: int
    minimum_card_width: int
    card_content_width: int
    task_area_minimum_width: int
    task_area_width: int
    task_text_available_width: int
    timer_area_minimum_width: int
    timer_area_width: int
    timer_text_available_width: int
    task_text_height: int
    content_height: int
    card_height: int
    action_area_x: int
    action_area_width: int
    overconstrained: bool


def calculate_card_width(viewport_width: int, list_spacing: int) -> int:
    """返回列表 viewport 内扣除两侧 item spacing 后的卡片宽度。"""

    return max(viewport_width - (max(list_spacing, 0) * 2), 0)


def calculate_task_card_layout(values: TaskCardLayoutInput) -> TaskCardLayout:
    """按现有挤压优先级计算卡片区域尺寸。

    正文先让出超过其动态最小宽度的空间，计时区随后从自然宽度压缩到最小
    宽度。viewport 再窄时仍保留两个区域的既有最小宽度。
    """

    card_width = calculate_card_width(values.viewport_width, values.list_spacing)
    card_content_width = max(
        card_width - max(values.card_frame_horizontal_inset, 0),
        0,
    )
    task_area_minimum_width = max(
        values.task_area_floor_width,
        min(
            values.task_area_maximum_minimum_width,
            max(values.task_natural_width, values.priority_natural_width),
        ),
    )
    timer_area_minimum_width = max(
        values.timer_base_minimum_width,
        values.timer_prefix_minimum_width,
        0,
    )
    timer_preferred_width = max(values.timer_natural_width, timer_area_minimum_width)
    spacing_width = max(values.main_layout_spacing, 0) * 2
    region_budget = max(
        card_content_width
        - max(values.complete_area_width, 0)
        - spacing_width,
        0,
    )
    minimum_region_width = task_area_minimum_width + timer_area_minimum_width
    minimum_card_width = (
        max(values.card_frame_horizontal_inset, 0)
        + max(values.complete_area_width, 0)
        + spacing_width
        + minimum_region_width
    )

    if region_budget >= task_area_minimum_width + timer_preferred_width:
        timer_area_width = timer_preferred_width
        task_area_width = region_budget - timer_area_width
    elif region_budget >= minimum_region_width:
        task_area_width = task_area_minimum_width
        timer_area_width = region_budget - task_area_width
    else:
        task_area_width = task_area_minimum_width
        timer_area_width = timer_area_minimum_width

    task_text_available_width = max(
        task_area_width - max(values.task_text_horizontal_inset, 0),
        0,
    )
    timer_text_available_width = max(
        timer_area_width - max(values.timer_text_horizontal_inset, 0),
        0,
    )

    logical_line_count = max(values.logical_line_count, 1)
    task_text_height = (
        logical_line_count * max(values.line_height, 0)
        + max(values.task_text_vertical_inset, 0)
    )
    content_height = (
        max(values.content_layout_vertical_inset, 0)
        + task_text_height
        + max(values.content_layout_spacing, 0)
        + max(values.priority_height, 0)
    )
    child_height = max(
        content_height,
        max(values.complete_area_height, 0),
        max(values.timer_height, 0),
    )
    card_height = max(
        values.card_minimum_height,
        max(values.card_frame_vertical_inset, 0)
        + max(values.main_layout_vertical_inset, 0)
        + child_height,
    )

    action_area_width = min(
        max(values.action_area_width, 0),
        card_content_width,
    )
    action_area_x = max(card_content_width - action_area_width, 0)

    return TaskCardLayout(
        card_width=card_width,
        minimum_card_width=minimum_card_width,
        card_content_width=card_content_width,
        task_area_minimum_width=task_area_minimum_width,
        task_area_width=task_area_width,
        task_text_available_width=task_text_available_width,
        timer_area_minimum_width=timer_area_minimum_width,
        timer_area_width=timer_area_width,
        timer_text_available_width=timer_text_available_width,
        task_text_height=task_text_height,
        content_height=content_height,
        card_height=card_height,
        action_area_x=action_area_x,
        action_area_width=action_area_width,
        overconstrained=region_budget < minimum_region_width,
    )


@dataclass(frozen=True)
class TaskDetailsWidthInput:
    """详情浮层宽度计算所需的普通数值。"""

    maximum_width: int
    natural_text_width: int
    scrollbar_reserve: int
    maximum_popup_width: int
    minimum_text_width: int
    horizontal_margin: int
    frame_width: int


@dataclass(frozen=True)
class TaskDetailsWidth:
    """详情正文、滚动区与外框宽度。"""

    text_width: int
    scroll_area_width: int
    popup_width: int


def calculate_task_details_width(
    values: TaskDetailsWidthInput,
) -> TaskDetailsWidth:
    """在屏幕可用宽度与既有上限内计算详情浮层宽度。"""

    horizontal_margin = max(values.horizontal_margin, 0)
    frame_width = max(values.frame_width, 0)
    scrollbar_reserve = max(values.scrollbar_reserve, 0)
    horizontal_overhead = (
        (horizontal_margin * 2) + frame_width + scrollbar_reserve
    )
    popup_width_limit = min(
        max(values.maximum_width, horizontal_overhead + 1),
        max(values.maximum_popup_width, horizontal_overhead + 1),
    )
    maximum_text_width = popup_width_limit - horizontal_overhead
    text_width = min(
        max(
            values.natural_text_width,
            min(max(values.minimum_text_width, 0), maximum_text_width),
        ),
        maximum_text_width,
    )
    scroll_area_width = text_width + scrollbar_reserve
    return TaskDetailsWidth(
        text_width=text_width,
        scroll_area_width=scroll_area_width,
        popup_width=text_width + horizontal_overhead,
    )


@dataclass(frozen=True)
class LayoutRect:
    """采用与 QRect 一致的含边界 right/bottom 语义。"""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + max(self.width, 0) - 1

    @property
    def bottom(self) -> int:
        return self.top + max(self.height, 0) - 1


@dataclass(frozen=True)
class TaskDetailsHeight:
    """详情浮层在高度限制下的边距与视口尺寸。"""

    vertical_margin: int
    viewport_height: int
    popup_height: int


def calculate_task_details_height(
    *,
    maximum_height: int,
    content_height: int,
    line_height: int,
    vertical_margin: int,
    frame_width: int,
) -> Optional[TaskDetailsHeight]:
    """压缩装饰边距并至少保留一个可显示像素。"""

    maximum_height = max(maximum_height, 0)
    content_height = max(content_height, 0)
    minimum_viewport_height = min(content_height, max(line_height, 0))
    margin_budget = max(
        maximum_height - max(frame_width, 0) - minimum_viewport_height,
        0,
    )
    resolved_margin = min(max(vertical_margin, 0), margin_budget // 2)
    frame_height = (resolved_margin * 2) + max(frame_width, 0)
    viewport_capacity = maximum_height - frame_height
    if viewport_capacity < 1:
        return None

    viewport_height = min(content_height, viewport_capacity)
    return TaskDetailsHeight(
        vertical_margin=resolved_margin,
        viewport_height=viewport_height,
        popup_height=viewport_height + frame_height,
    )


@dataclass(frozen=True)
class TaskDetailsPlacementInput:
    """详情浮层定位所需的屏幕与卡片几何。"""

    available: LayoutRect
    card: LayoutRect
    task_origin_x: int
    task_origin_y: int
    popup_width: int
    content_height: int
    line_height: int
    gap: int
    minimum_vertical_space: int
    vertical_margin: int
    frame_width: int


@dataclass(frozen=True)
class TaskDetailsPlacement:
    """详情浮层的最终位置与高度布局。"""

    side: Literal["above", "below", "left", "right"]
    x: int
    y: int
    height: TaskDetailsHeight


def calculate_task_details_placement(
    values: TaskDetailsPlacementInput,
) -> Optional[TaskDetailsPlacement]:
    """按现有上下优先、空间不足时转移到侧面的规则定位详情。"""

    gap = max(values.gap, 0)
    popup_width = max(values.popup_width, 0)
    available = values.available
    card = values.card
    space_below = max(available.bottom - card.bottom - gap, 0)
    space_above = max(card.top - available.top - gap, 0)
    space_right = max(available.right - card.right - gap, 0)
    space_left = max(card.left - available.left - gap, 0)

    if (
        max(space_above, space_below) < values.minimum_vertical_space
        and max(space_left, space_right) >= popup_width
    ):
        height = calculate_task_details_height(
            maximum_height=available.height,
            content_height=values.content_height,
            line_height=values.line_height,
            vertical_margin=values.vertical_margin,
            frame_width=values.frame_width,
        )
        if height is None:
            return None

        if space_right >= popup_width:
            side: Literal["left", "right"] = "right"
            popup_x = card.right + gap + 1
        else:
            side = "left"
            popup_x = card.left - gap - popup_width
        maximum_y = max(
            available.top,
            available.bottom - height.popup_height + 1,
        )
        popup_y = min(max(values.task_origin_y, available.top), maximum_y)
        return TaskDetailsPlacement(side, popup_x, popup_y, height)

    show_below = space_below >= space_above
    vertical_space = space_below if show_below else space_above
    height = calculate_task_details_height(
        maximum_height=vertical_space,
        content_height=values.content_height,
        line_height=values.line_height,
        vertical_margin=values.vertical_margin,
        frame_width=values.frame_width,
    )
    if height is None:
        return None

    maximum_x = max(
        available.left,
        available.right - popup_width + 1,
    )
    popup_x = min(max(values.task_origin_x, available.left), maximum_x)
    if show_below:
        side = "below"
        popup_y = card.bottom + gap + 1
    else:
        side = "above"
        popup_y = card.top - gap - height.popup_height
    return TaskDetailsPlacement(side, popup_x, popup_y, height)


__all__ = [
    "LayoutRect",
    "TaskCardLayout",
    "TaskCardLayoutInput",
    "TaskDetailsHeight",
    "TaskDetailsPlacement",
    "TaskDetailsPlacementInput",
    "TaskDetailsWidth",
    "TaskDetailsWidthInput",
    "calculate_card_width",
    "calculate_task_card_layout",
    "calculate_task_details_height",
    "calculate_task_details_placement",
    "calculate_task_details_width",
]
