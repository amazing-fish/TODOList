"""任务卡片纯布局规则测试，不需要 QApplication。"""
from __future__ import annotations

import unittest

from todo_app.constants import (
    TASK_ACTION_AREA_WIDTH,
    TASK_AREA_FLOOR_WIDTH,
    TASK_AREA_MAXIMUM_MINIMUM_WIDTH,
    TASK_CARD_HORIZONTAL_SPACING,
    TASK_CARD_LIST_GAP,
    TASK_CARD_MINIMUM_HEIGHT,
    TASK_CONTENT_VERTICAL_SPACING,
    TASK_DETAILS_FRAME_WIDTH,
    TASK_DETAILS_HORIZONTAL_MARGIN,
    TASK_DETAILS_MAXIMUM_WIDTH,
    TASK_DETAILS_MINIMUM_TEXT_WIDTH,
    TASK_TIMER_MINIMUM_WIDTH,
)
from todo_app.layout import (
    TaskCardLayoutInput,
    TaskDetailsWidthInput,
    calculate_task_card_layout,
    calculate_task_details_width,
)


class TaskCardLayoutTest(unittest.TestCase):
    def test_wide_viewport_keeps_task_and_timer_at_natural_width(self) -> None:
        values = self._card_values(viewport_width=500)

        layout = calculate_task_card_layout(values)

        self.assertGreaterEqual(layout.task_area_width, values.task_natural_width)
        self.assertEqual(layout.timer_area_width, values.timer_natural_width)
        self.assertFalse(layout.overconstrained)

    def test_narrow_viewport_shrinks_task_extra_before_timer(self) -> None:
        values = self._card_values(viewport_width=306)

        layout = calculate_task_card_layout(values)

        self.assertEqual(
            layout.task_area_width,
            layout.task_area_minimum_width,
        )
        self.assertEqual(layout.timer_area_width, 70)
        self.assertGreater(
            layout.timer_area_width,
            layout.timer_area_minimum_width,
        )
        self.assertLess(layout.timer_area_width, values.timer_natural_width)
        self.assertFalse(layout.overconstrained)

    def test_extremely_narrow_viewport_preserves_area_minimums(self) -> None:
        layout = calculate_task_card_layout(
            self._card_values(viewport_width=250)
        )

        self.assertEqual(
            layout.task_area_width,
            layout.task_area_minimum_width,
        )
        self.assertEqual(
            layout.timer_area_width,
            layout.timer_area_minimum_width,
        )
        self.assertTrue(layout.overconstrained)

    def test_multiple_logical_lines_determine_card_height(self) -> None:
        layout = calculate_task_card_layout(
            self._card_values(
                viewport_width=500,
                logical_line_count=3,
            )
        )

        self.assertEqual(layout.task_text_height, 51)
        self.assertEqual(layout.content_height, 75)
        self.assertEqual(layout.card_height, 101)

    def test_details_popup_width_is_capped(self) -> None:
        layout = calculate_task_details_width(
            TaskDetailsWidthInput(
                maximum_width=800,
                natural_text_width=500,
                scrollbar_reserve=16,
                maximum_popup_width=TASK_DETAILS_MAXIMUM_WIDTH,
                minimum_text_width=TASK_DETAILS_MINIMUM_TEXT_WIDTH,
                horizontal_margin=TASK_DETAILS_HORIZONTAL_MARGIN,
                frame_width=TASK_DETAILS_FRAME_WIDTH,
            )
        )

        self.assertEqual(layout.text_width, 318)
        self.assertEqual(layout.scroll_area_width, 334)
        self.assertEqual(layout.popup_width, TASK_DETAILS_MAXIMUM_WIDTH)

    @staticmethod
    def _card_values(
        *,
        viewport_width: int,
        logical_line_count: int = 1,
    ) -> TaskCardLayoutInput:
        return TaskCardLayoutInput(
            viewport_width=viewport_width,
            list_spacing=TASK_CARD_LIST_GAP // 2,
            card_frame_horizontal_inset=26,
            card_frame_vertical_inset=26,
            main_layout_spacing=TASK_CARD_HORIZONTAL_SPACING,
            main_layout_vertical_inset=0,
            complete_area_width=32,
            complete_area_height=32,
            task_natural_width=200,
            priority_natural_width=40,
            task_area_floor_width=TASK_AREA_FLOOR_WIDTH,
            task_area_maximum_minimum_width=(
                TASK_AREA_MAXIMUM_MINIMUM_WIDTH
            ),
            task_text_horizontal_inset=0,
            task_text_vertical_inset=0,
            logical_line_count=logical_line_count,
            line_height=17,
            content_layout_vertical_inset=0,
            content_layout_spacing=TASK_CONTENT_VERTICAL_SPACING,
            priority_height=20,
            timer_natural_width=100,
            timer_base_minimum_width=TASK_TIMER_MINIMUM_WIDTH,
            timer_prefix_minimum_width=48,
            timer_text_horizontal_inset=0,
            timer_height=20,
            action_area_width=TASK_ACTION_AREA_WIDTH,
            card_minimum_height=TASK_CARD_MINIMUM_HEIGHT,
        )


if __name__ == "__main__":
    unittest.main()
