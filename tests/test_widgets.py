"""待办卡片布局与交互测试。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QEnterEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QVBoxLayout,
    QWidget,
)

from todo_app.constants import DARK_THEME_COLORS, LIGHT_THEME_COLORS  # noqa: E402
from todo_app.fonts import apply_application_font  # noqa: E402
from todo_app.main_window import ModernTodoAppWindow  # noqa: E402
from todo_app.widgets import TodoItemWidget  # noqa: E402


class TodoItemWidgetLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        apply_application_font()

    def test_hover_keeps_text_clear_and_content_geometry_stable(self) -> None:
        host = QWidget()
        host_layout = QVBoxLayout(host)
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": "这是一段很长很长的任务文字，用于检查窄窗口下的显示效果",
                "priority": "中",
                "completed": False,
                "dueDate": None,
            }
        )
        widget.setFixedSize(240, 110)
        host_layout.addWidget(widget)
        host.setFixedSize(262, 132)
        host.show()
        self.addCleanup(host.close)
        self.app.processEvents()

        idle_task_geometry = widget.task_text_label.geometry()
        idle_timer_geometry = widget.timer_display_label.geometry()
        self._assert_each_logical_line_fits(widget)

        widget.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()

        self.assertTrue(widget.edit_button.isVisible())
        self.assertTrue(widget.delete_button.isVisible())
        self.assertEqual(widget.task_text_label.geometry(), idle_task_geometry)
        self.assertEqual(widget.timer_display_label.geometry(), idle_timer_geometry)
        self._assert_each_logical_line_fits(widget)

        widget.leaveEvent(QEvent(QEvent.Type.Leave))
        self.app.processEvents()
        self.assertFalse(widget.edit_button.isVisible())
        self.assertFalse(widget.delete_button.isVisible())
        self.assertEqual(widget.task_text_label.geometry(), idle_task_geometry)
        self.assertEqual(widget.timer_display_label.geometry(), idle_timer_geometry)

    def test_task_text_preserves_line_breaks_and_elides_each_logical_line(self) -> None:
        original_text = (
            "第一行很长的中文任务内容需要独立省略" * 3
            + "\r\n"
            + "第二行同样很长并且不能折成额外视觉行" * 3
            + "\n\n"
            + "continuousEnglishTextWithoutSpaces" * 4
        )
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": original_text,
                "priority": "中",
                "completed": False,
                "dueDate": None,
            }
        )
        widget.setFixedWidth(260)
        widget.show()
        self.addCleanup(widget.close)
        self.app.processEvents()
        widget.resize(260, widget.requiredHeight())
        self.app.processEvents()

        self.assertFalse(widget.task_text_label.wordWrap())
        self.assertEqual(widget.task_text_label.text(), original_text)
        self.assertEqual(widget.todo_item["text"], original_text)
        displayed_lines = widget.task_text_label.displayed_lines()
        self.assertEqual(len(displayed_lines), 4)
        self.assertTrue(displayed_lines[0].endswith("…"))
        self.assertTrue(displayed_lines[1].endswith("…"))
        self.assertEqual(displayed_lines[2], "")
        self.assertTrue(displayed_lines[3].endswith("…"))
        self.assertEqual(widget.task_text_label.toolTip(), "")
        self.assertTrue(widget.task_text_label.needs_details())
        self._assert_each_logical_line_fits(widget)

    def test_task_details_popup_preserves_plain_text_without_stealing_focus(self) -> None:
        original_text = (
            "第一行包含 <b>标签</b>、& 符号和引号 \"内容\""
            "，并且足够长以验证自动换行"
            "\n第二行保持原始换行"
        )
        host = QWidget()
        host_layout = QVBoxLayout(host)
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": original_text,
                "priority": "中",
                "completed": False,
                "dueDate": None,
            }
        )
        widget.setFixedSize(280, widget.requiredHeight())
        host_layout.addWidget(widget)
        host.setFixedSize(302, widget.height() + 22)
        host.show()
        self.addCleanup(host.close)
        self.app.processEvents()

        widget.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        card_size = widget.size()
        task_geometry = widget.task_text_label.geometry()
        timer_geometry = widget.timer_display_label.geometry()
        widget.complete_button.setFocus()
        focused_widget = self.app.focusWidget()
        self.assertIs(focused_widget, widget.complete_button)
        widget.task_text_label.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()

        popup = widget.task_details_popup
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup.details_label.text(), original_text)
        self.assertEqual(popup.details_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertTrue(popup.details_label.wordWrap())
        self.assertLessEqual(popup.width(), 360)
        self.assertTrue(
            popup.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.assertEqual(self.app.focusWidget(), focused_widget)
        self.assertEqual(widget.task_text_label.toolTip(), "")
        self.assertEqual(widget.size(), card_size)
        self.assertEqual(widget.task_text_label.geometry(), task_geometry)
        self.assertEqual(widget.timer_display_label.geometry(), timer_geometry)

        actions_top_left = widget.actions_container.mapToGlobal(QPoint(0, 0))
        actions_rect = QRect(actions_top_left, widget.actions_container.size())
        self.assertFalse(popup.frameGeometry().intersects(actions_rect))

        widget.task_text_label.leaveEvent(QEvent(QEvent.Type.Leave))
        self.app.processEvents()
        self.assertFalse(popup.isVisible())

    def test_task_details_requirement_tracks_elision_multiline_and_theme(self) -> None:
        long_text = "continuousEnglishTextWithoutSpaces" * 2
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": long_text,
                "priority": "中",
                "completed": False,
                "dueDate": None,
            }
        )
        widget.setFixedHeight(110)
        widget.resize(260, 110)
        widget.show()
        self.addCleanup(widget.close)
        self.app.processEvents()

        self.assertTrue(widget.task_text_label.needs_details())
        widget.resize(900, 110)
        widget.layout().invalidate()
        widget.layout().activate()
        self.app.processEvents()
        self.assertFalse(
            widget.task_text_label.needs_details(),
            (
                widget.task_text_label.width(),
                widget.task_text_label.natural_width(),
                widget.task_text_label.displayed_lines(),
            ),
        )

        short_widget = TodoItemWidget(
            {
                "id": 2,
                "text": "短任务",
                "priority": "低",
                "completed": False,
                "dueDate": None,
            }
        )
        short_widget.setFixedSize(420, 110)
        short_widget.show()
        self.addCleanup(short_widget.close)
        self.app.processEvents()
        short_widget.task_text_label.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()
        self.assertFalse(short_widget.task_details_popup.isVisible())

        multiline_widget = TodoItemWidget(
            {
                "id": 3,
                "text": "第一行\n第二行",
                "priority": "高",
                "completed": False,
                "dueDate": None,
            },
            palette=LIGHT_THEME_COLORS,
        )
        multiline_widget.setFixedSize(900, multiline_widget.requiredHeight())
        multiline_widget.show()
        self.addCleanup(multiline_widget.close)
        self.app.processEvents()
        self.assertTrue(multiline_widget.task_text_label.needs_details())

        multiline_widget.apply_palette(DARK_THEME_COLORS)
        multiline_widget.task_text_label.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()
        popup_style = multiline_widget.task_details_popup.styleSheet()
        self.assertIn(DARK_THEME_COLORS.primary_item_bg, popup_style)
        self.assertIn(DARK_THEME_COLORS.text_primary, popup_style)
        self.assertEqual(
            multiline_widget.task_details_popup.details_label.text(),
            "第一行\n第二行",
        )
        self.assertEqual(
            multiline_widget.task_details_popup.scroll_area.verticalScrollBar().maximum(),
            0,
        )
        non_scrollable_wheel = self._wheel_event(-120)
        multiline_widget.task_text_label.wheelEvent(non_scrollable_wheel)
        self.assertFalse(non_scrollable_wheel.isAccepted())

    def test_oversized_task_details_stays_off_card_and_scrolls(self) -> None:
        original_text = "超长任务正文需要保持完整可浏览" * 400
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": original_text,
                "priority": "高",
                "completed": False,
                "dueDate": None,
            }
        )
        screen_geometry = widget.screen().availableGeometry()
        widget.setFixedSize(280, 110)
        widget.move(
            screen_geometry.left() + 10,
            screen_geometry.center().y() - (widget.height() // 2),
        )
        widget.show()
        self.addCleanup(widget.close)
        self.app.processEvents()

        widget.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        widget.task_text_label.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()

        popup = widget.task_details_popup
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup.details_label.text(), original_text)
        self.assertLessEqual(popup.width(), 360)
        self.assertLessEqual(popup.height(), screen_geometry.height())
        self.assertTrue(screen_geometry.contains(popup.frameGeometry()))
        card_rect = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
        self.assertFalse(popup.frameGeometry().intersects(card_rect))

        scrollbar = popup.scroll_area.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        self.assertEqual(scrollbar.value(), 0)
        scrollable_wheel = self._wheel_event(-120)
        widget.task_text_label.wheelEvent(scrollable_wheel)
        self.assertTrue(scrollable_wheel.isAccepted())
        self.assertGreater(scrollbar.value(), 0)

    def test_task_details_popup_reflows_to_narrow_available_width(self) -> None:
        original_text = "窄屏详情必须在屏幕内重新换行并保持完整可滚动" * 80
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": original_text,
                "priority": "中",
                "completed": False,
                "dueDate": None,
            }
        )
        widget.setFixedSize(280, 110)
        widget.move(10, 245)
        widget.show()
        self.addCleanup(widget.close)
        self.app.processEvents()

        narrow_available = QRect(0, 0, 320, 600)
        with patch.object(widget, "screen") as screen:
            screen.return_value.availableGeometry.return_value = narrow_available
            widget.task_text_label.enterEvent(
                QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
            )
            self.app.processEvents()

            popup = widget.task_details_popup
            self.assertTrue(popup.isVisible())
            self.assertLessEqual(popup.width(), narrow_available.width())
            self.assertTrue(narrow_available.contains(popup.frameGeometry()))
            self.assertEqual(popup.details_label.text(), original_text)
            self.assertEqual(
                popup.details_label.height(),
                popup.details_label.heightForWidth(popup.details_label.width()),
            )
            self.assertGreater(
                popup.scroll_area.verticalScrollBar().maximum(),
                0,
            )

    def test_task_details_popup_fits_tight_vertical_space(self) -> None:
        original_text = "极小纵向空间中的详情仍需保持在屏幕内" * 80
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": original_text,
                "priority": "高",
                "completed": False,
                "dueDate": None,
            }
        )
        widget.setFixedSize(280, 110)
        widget.move(20, 27)
        widget.show()
        self.addCleanup(widget.close)
        self.app.processEvents()

        card_rect = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
        tight_available = QRect(
            card_rect.left() - 20,
            card_rect.top() - 27,
            320,
            160,
        )
        with patch.object(widget, "screen") as screen:
            screen.return_value.availableGeometry.return_value = tight_available
            widget.task_text_label.enterEvent(
                QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
            )
            self.app.processEvents()

            popup = widget.task_details_popup
            self.assertTrue(popup.isVisible())
            self.assertTrue(tight_available.contains(popup.frameGeometry()))
            self.assertFalse(popup.frameGeometry().intersects(card_rect))
            self.assertGreater(popup.scroll_area.viewport().height(), 0)
            self.assertGreater(
                popup.scroll_area.verticalScrollBar().maximum(),
                0,
            )

    def test_timer_text_growth_keeps_per_line_task_visible(self) -> None:
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
        host = QWidget()
        host_layout = QVBoxLayout(host)
        widget = TodoItemWidget(
            {
                "id": 1,
                "text": "这是一段很长的任务文字",
                "priority": "中",
                "completed": False,
                "dueDate": (now + timedelta(seconds=1)).isoformat(),
            }
        )
        widget.setFixedSize(320, 110)
        host_layout.addWidget(widget)
        host.setFixedSize(342, 132)
        host.show()
        self.addCleanup(host.close)

        widget.update_timer_display(now)
        self.app.processEvents()
        self.assertEqual(widget.timer_display_label.text(), "剩余: 1秒")
        initial_details_required = widget.task_text_label.needs_details()
        widget.task_text_label.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()
        self.assertFalse(widget.task_details_popup.isVisible())

        widget.update_timer_display(now + timedelta(days=100_000))
        self.app.processEvents()

        self.assertTrue(widget.timer_display_label.text().startswith("已到期"))
        self.assertEqual(
            (initial_details_required, widget.task_text_label.needs_details()),
            (False, True),
            (
                widget.task_text_label.width(),
                widget.task_text_label.natural_width(),
                widget.task_text_label.displayed_lines(),
            ),
        )
        self.assertTrue(widget.task_details_popup.isVisible())
        self.assertEqual(
            widget.task_details_popup.details_label.text(),
            widget.original_text,
        )
        self._assert_each_logical_line_fits(widget)

    def test_timer_status_full_text_is_preserved_for_supported_states(self) -> None:
        now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        cases = (
            ({"completed": True, "dueDate": None}, "已完成"),
            ({"completed": False, "dueDate": None}, "无截止日期"),
            ({"completed": False, "dueDate": "not-a-date"}, "日期格式错误!"),
            (
                {
                    "completed": False,
                    "dueDate": None,
                    "snoozeUntil": (now + timedelta(days=2)).isoformat(),
                },
                "推迟: 2天",
            ),
        )

        for overrides, expected_text in cases:
            with self.subTest(expected_text=expected_text):
                todo = {
                    "id": 1,
                    "text": "检查计时状态",
                    "priority": "中",
                    "completed": False,
                    "dueDate": None,
                    "snoozeUntil": None,
                    **overrides,
                }
                widget = TodoItemWidget(todo)
                widget.setFixedSize(420, 110)
                widget.show()
                self.addCleanup(widget.close)

                with patch("builtins.print"):
                    widget.update_timer_display(now)
                self.app.processEvents()

                self.assertEqual(widget.timer_display_label.full_text, expected_text)
                self.assertEqual(widget.timer_display_label.text(), expected_text)
                self.assertEqual(widget.timer_display_label.toolTip(), "")

    def _assert_each_logical_line_fits(self, widget: TodoItemWidget) -> None:
        label = widget.task_text_label
        self.assertFalse(label.wordWrap())
        available_width = label.contentsRect().width()
        for displayed_line in label.displayed_lines():
            with self.subTest(displayed_line=displayed_line):
                self.assertLessEqual(
                    label.fontMetrics().horizontalAdvance(displayed_line),
                    available_width,
                )
        required_height = label.heightForWidth(label.contentsRect().width())
        self.assertGreater(required_height, 0)
        self.assertGreaterEqual(label.contentsRect().height(), required_height)

    @staticmethod
    def _wheel_event(delta: int) -> QWheelEvent:
        return QWheelEvent(
            QPointF(1, 1),
            QPointF(1, 1),
            QPoint(0, 0),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )


class TodoListCardIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        apply_application_font()

    def test_main_controls_and_card_share_application_font_family(self) -> None:
        from todo_app.constants import APP_FONT_FAMILY

        window = self._create_window()
        card = window.list_widget.itemWidget(window.list_widget.item(0))
        representative_widgets = (
            window.filter_label,
            window.filter_combo,
            window.sort_label,
            window.sort_combo,
            card.task_text_label,
            card.priority_label,
            card.timer_display_label,
        )

        self.assertEqual(QApplication.font().family(), APP_FONT_FAMILY)
        for widget in representative_widgets:
            with self.subTest(widget=type(widget).__name__):
                self.assertEqual(widget.font().family(), APP_FONT_FAMILY)

    def test_default_width_card_uses_viewport_and_hover_actions_overlay_timer(self) -> None:
        window = self._create_window()
        window.resize(320, 640)
        window.show()
        self.app.processEvents()

        item = window.list_widget.item(0)
        card = window.list_widget.itemWidget(item)
        viewport = window.list_widget.viewport()

        self.assertLessEqual(card.width(), viewport.width())
        self.assertLessEqual(
            window.list_widget.visualItemRect(item).right(),
            viewport.rect().right(),
        )
        self.assertEqual(card.task_text_label.minimumWidth(), 150)
        self.assertGreaterEqual(card.task_text_label.width(), 150)
        self.assertGreaterEqual(card.timer_display_label.minimumWidth(), 50)
        self.assertGreaterEqual(card.timer_display_label.width(), 50)

        idle_task_geometry = card.task_text_label.geometry()
        idle_timer_geometry = card.timer_display_label.geometry()
        card.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()

        self.assertFalse(card.edit_button.visibleRegion().isEmpty())
        self.assertFalse(card.delete_button.visibleRegion().isEmpty())
        for button in (card.edit_button, card.delete_button):
            self.assertGreaterEqual(button.width(), 28)
            self.assertGreaterEqual(button.height(), 26)
            self.assertFalse(button.icon().isNull())
        self.assertIs(
            card.childAt(
                card.edit_button.mapTo(card, card.edit_button.rect().center())
            ),
            card.edit_button,
        )
        self.assertIs(
            card.childAt(
                card.delete_button.mapTo(card, card.delete_button.rect().center())
            ),
            card.delete_button,
        )
        self.assertTrue(
            card.actions_container.geometry().intersects(
                card.timer_display_label.geometry()
            )
        )
        self.assertEqual(card.task_text_label.geometry(), idle_task_geometry)
        self.assertEqual(card.timer_display_label.geometry(), idle_timer_geometry)

    def test_todo_list_disables_item_selection_frame(self) -> None:
        window = self._create_window()

        self.assertEqual(
            window.list_widget.selectionMode(),
            QAbstractItemView.SelectionMode.NoSelection,
        )

    def test_narrow_timer_elides_from_right_and_preserves_status_prefix(self) -> None:
        now = datetime.now(timezone.utc)
        todos = [
            {
                "id": 1,
                "text": "很长的未来任务名称，用于验证窄卡片计时显示",
                "priority": "中",
                "completed": False,
                "dueDate": (now + timedelta(days=123_456)).isoformat(),
                "createdAt": now.isoformat(),
                "snoozeUntil": None,
            },
            {
                "id": 2,
                "text": "很长的逾期任务名称，用于验证窄卡片计时显示",
                "priority": "高",
                "completed": False,
                "dueDate": (now - timedelta(days=123_456)).isoformat(),
                "createdAt": now.isoformat(),
                "snoozeUntil": None,
            },
        ]
        window = self._create_window(todos=todos)
        window.resize(320, 640)
        window.show()
        self.app.processEvents()

        for index, prefix in enumerate(("剩余", "已到期")):
            with self.subTest(prefix=prefix):
                item = window.list_widget.item(index)
                card = window.list_widget.itemWidget(item)
                displayed_text = card.timer_display_label.text()
                available_width = card.timer_display_label.contentsRect().width()

                self.assertLessEqual(card.width(), window.list_widget.viewport().width())
                self.assertTrue(displayed_text.startswith(prefix))
                self.assertTrue(displayed_text.endswith("…"))
                self.assertLessEqual(
                    card.timer_display_label.fontMetrics().horizontalAdvance(displayed_text),
                    available_width,
                )
                self.assertNotEqual(displayed_text, card.timer_display_label.full_text)
                self.assertEqual(
                    card.timer_display_label.toolTip(),
                    card.timer_display_label.full_text,
                )

    def test_short_task_yields_space_for_full_timer_at_minimum_window_width(self) -> None:
        now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
        todo = {
            "id": 1,
            "text": "短任务",
            "priority": "中",
            "completed": False,
            "dueDate": (now + timedelta(days=123, hours=4)).isoformat(),
            "createdAt": now.isoformat(),
            "snoozeUntil": None,
        }
        window = self._create_window(todos=[todo])
        window.resize(320, 640)
        window.show()
        self._settle_list_layout(window)

        item = window.list_widget.item(0)
        card = window.list_widget.itemWidget(item)
        card.update_timer_display(now)
        self._settle_list_layout(window)

        timer = card.timer_display_label
        self.assertEqual(timer.full_text, "剩余: 123天 4时")
        self.assertEqual(timer.text(), timer.full_text)
        self.assertEqual(timer.toolTip(), "")
        self.assertLess(card.content_container.minimumWidth(), 150)
        self.assertGreaterEqual(timer.width(), timer.sizeHint().width())
        self.assertFalse(window.list_widget.horizontalScrollBar().isVisible())

    def test_multiple_cards_have_real_vertical_gap_with_unpainted_background(self) -> None:
        window = self._create_window(todo_count=2)
        window.resize(320, 640)
        window.show()
        self.app.processEvents()

        first_item = window.list_widget.item(0)
        second_item = window.list_widget.item(1)
        first_card = window.list_widget.itemWidget(first_item)
        second_card = window.list_widget.itemWidget(second_item)
        card_gap = second_card.geometry().top() - first_card.geometry().bottom() - 1

        self.assertEqual(card_gap, window.list_widget.spacing() * 2)
        self.assertEqual(card_gap, 8)
        self.assertGreaterEqual(first_item.sizeHint().height(), first_card.minimumHeight())
        self.assertGreaterEqual(second_item.sizeHint().height(), second_card.minimumHeight())

        viewport_image = window.list_widget.viewport().grab().toImage()
        sample_x = first_card.geometry().center().x()
        card_y = first_card.geometry().top() + 5
        gap_y = first_card.geometry().bottom() + 1 + card_gap // 2
        self.assertNotEqual(
            viewport_image.pixelColor(sample_x, card_y).rgba(),
            viewport_image.pixelColor(sample_x, gap_y).rgba(),
        )

    def test_hidden_scrollbar_keeps_card_outer_margins_symmetric(self) -> None:
        for todo_count in (1, 2):
            with self.subTest(todo_count=todo_count):
                window = self._create_window(todo_count=todo_count)
                window.resize(320, 640)
                window.show()
                self._settle_list_layout(window)

                self.assertFalse(window.list_widget.verticalScrollBar().isVisible())
                left_margin, right_margin = self._card_outer_margins(window)
                self.assertLessEqual(abs(left_margin - right_margin), 1)
                self.assertEqual(
                    window.list_widget.horizontalScrollBarPolicy(),
                    Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
                )

    def test_empty_placeholder_does_not_force_vertical_scrollbar(self) -> None:
        window = self._create_window(todo_count=0)
        window.resize(320, 640)
        window.show()
        self._settle_list_layout(window)

        scrollbar = window.list_widget.verticalScrollBar()
        self.assertFalse(scrollbar.isVisible())
        self.assertEqual(scrollbar.minimum(), scrollbar.maximum())
        self.assertEqual(window.list_widget.viewportMargins().right(), 8)

    def test_scrollbar_visibility_transition_preserves_outer_margin_contract(self) -> None:
        window = self._create_window(todo_count=6)
        window.resize(320, 560)
        window.show()

        for height, expected_visible in ((560, True), (900, False), (560, True)):
            with self.subTest(height=height, expected_visible=expected_visible):
                window.resize(320, height)
                self._settle_list_layout(window)

                scrollbar = window.list_widget.verticalScrollBar()
                self.assertEqual(scrollbar.isVisible(), expected_visible)
                left_margin, right_margin = self._card_outer_margins(window)
                self.assertLessEqual(abs(left_margin - right_margin), 1)
                self.assertEqual(scrollbar.width(), 8)
                self.assertFalse(window.list_widget.horizontalScrollBar().isVisible())

    def test_task_count_transition_preserves_outer_margin_contract(self) -> None:
        window = self._create_window(todo_count=6)
        window.resize(320, 640)
        window.show()
        all_todos = [todo.copy() for todo in window.todos]

        for todo_count, expected_visible in ((2, False), (6, True), (1, False)):
            with self.subTest(
                todo_count=todo_count,
                expected_visible=expected_visible,
            ):
                window.todos = [
                    todo.copy() for todo in all_todos[:todo_count]
                ]
                window.update_list_widget()
                self._settle_list_layout(window)

                scrollbar = window.list_widget.verticalScrollBar()
                self.assertEqual(scrollbar.isVisible(), expected_visible)
                left_margin, right_margin = self._card_outer_margins(window)
                self.assertLessEqual(abs(left_margin - right_margin), 1)
                self.assertFalse(window.list_widget.horizontalScrollBar().isVisible())

    def test_per_line_elision_tracks_viewport_across_rapid_resizes(self) -> None:
        now = datetime.now(timezone.utc)
        multiline_text = (
            "第一段任务内容保留开头并在不足时独立省略" * 2
            + "\r\n"
            + "第二段保留换行并在自己的行尾省略" * 2
            + "\n"
            + "第三段同样只占一个视觉行" * 2
        )
        long_chinese = "很长的中文任务内容" * 4
        long_unbroken_english = "continuousEnglishTextWithoutSpaces" * 2
        common_fields = {
            "priority": "中",
            "completed": False,
            "dueDate": (now + timedelta(days=123)).isoformat(),
            "createdAt": now.isoformat(),
            "snoozeUntil": None,
        }
        expected_texts = (
            multiline_text,
            long_chinese,
            long_unbroken_english,
            "相邻短任务",
        )
        window = self._create_window(
            todos=[
                {**common_fields, "id": index + 1, "text": text}
                for index, text in enumerate(expected_texts)
            ]
        )
        window.resize(900, 640)
        window.show()
        self._settle_list_layout(window)
        wide_heights = self._card_heights(window)
        expected_logical_lines = [
            text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            for text in expected_texts
        ]
        for index, logical_lines in enumerate(expected_logical_lines):
            card = window.list_widget.itemWidget(window.list_widget.item(index))
            self.assertEqual(card.task_text_label.displayed_lines(), logical_lines)
            self.assertEqual(card.task_text_label.toolTip(), "")

        for width in (640, 420, 320):
            window.resize(width, 640)
        self._settle_list_layout(window)
        narrow_heights = self._card_heights(window)

        for index, original_text in enumerate(expected_texts):
            with self.subTest(index=index):
                item = window.list_widget.item(index)
                card = window.list_widget.itemWidget(item)
                label = card.task_text_label
                self.assertLessEqual(card.width(), window.list_widget.viewport().width())
                self.assertEqual(label.text(), original_text)
                self.assertEqual(card.todo_item["text"], original_text)
                self.assertEqual(window.todos[index]["text"], original_text)
                self.assertFalse(label.wordWrap())
                displayed_lines = label.displayed_lines()
                self.assertEqual(len(displayed_lines), len(expected_logical_lines[index]))
                for displayed_line in displayed_lines:
                    self.assertLessEqual(
                        label.fontMetrics().horizontalAdvance(displayed_line),
                        label.contentsRect().width(),
                    )
                self.assertEqual(item.sizeHint().height(), card.height())
                self.assertFalse(window.list_widget.horizontalScrollBar().isVisible())
                required_height = label.heightForWidth(label.contentsRect().width())
                self.assertGreaterEqual(label.contentsRect().height(), required_height)

        self.assertEqual(narrow_heights, wide_heights)
        self.assertGreater(narrow_heights[0], narrow_heights[3])
        self.assertEqual(narrow_heights[1], narrow_heights[3])
        self.assertEqual(narrow_heights[2], narrow_heights[3])
        for index in range(3):
            card = window.list_widget.itemWidget(window.list_widget.item(index))
            self.assertTrue(
                any(line.endswith("…") for line in card.task_text_label.displayed_lines())
            )
            self.assertEqual(card.task_text_label.toolTip(), "")
            self.assertTrue(card.task_text_label.needs_details())
        self._assert_card_gaps(window)

        first_card = window.list_widget.itemWidget(window.list_widget.item(0))
        idle_task_geometry = first_card.task_text_label.geometry()
        idle_timer_geometry = first_card.timer_display_label.geometry()
        first_card.enterEvent(
            QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
        )
        self.app.processEvents()
        self.assertEqual(first_card.task_text_label.geometry(), idle_task_geometry)
        self.assertEqual(first_card.timer_display_label.geometry(), idle_timer_geometry)
        first_card.leaveEvent(QEvent(QEvent.Type.Leave))

        for width in (500, 320, 900):
            window.resize(width, 640)
        self._settle_list_layout(window)
        self.assertEqual(self._card_heights(window), wide_heights)
        for index, logical_lines in enumerate(expected_logical_lines):
            card = window.list_widget.itemWidget(window.list_widget.item(index))
            self.assertEqual(card.task_text_label.displayed_lines(), logical_lines)
            self.assertEqual(card.task_text_label.toolTip(), "")
            self.assertEqual(
                card.task_text_label.needs_details(),
                len(logical_lines) > 1,
            )
        self._assert_card_gaps(window)

    def test_filter_options_are_never_elided_at_minimum_window_width(self) -> None:
        window = self._create_window(todo_count=0)
        window.resize(320, 640)
        window.show()
        self._settle_list_layout(window)

        for index in range(window.filter_combo.count()):
            with self.subTest(option=window.filter_combo.itemText(index)):
                window.filter_combo.setCurrentIndex(index)
                self._settle_list_layout(window)
                option = QStyleOptionComboBox()
                window.filter_combo.initStyleOption(option)
                self.assertEqual(option.currentText, window.filter_combo.currentText())
                self.assertNotIn("…", option.currentText)

    def test_add_button_icon_has_transparent_background_and_theme_plus_color(self) -> None:
        window = self._create_window(todo_count=0)
        window._on_theme_changed(DARK_THEME_COLORS)
        window.show()
        self._settle_list_layout(window)

        image = window.add_button.icon().pixmap(window.add_button.iconSize()).toImage()
        opaque_pixels = sum(
            image.pixelColor(x, y).alpha() > 0
            for x in range(image.width())
            for y in range(image.height())
        )
        center_color = image.pixelColor(image.width() // 2, image.height() // 2)

        self.assertLess(opaque_pixels, image.width() * image.height() // 2)
        self.assertEqual(center_color.name(), QColor(DARK_THEME_COLORS.inverse_text).name())

    def test_minimum_width_controls_keep_sort_combo_and_arrow_visible(self) -> None:
        window = self._create_window(todo_count=0)
        window.resize(320, 640)
        window.show()
        self._settle_list_layout(window)

        central_widget = window.centralWidget()
        controls_left = window.filter_label.mapTo(
            central_widget, QPoint(0, 0)
        ).x()
        controls_right = central_widget.width() - controls_left
        controls = (
            window.filter_label,
            window.filter_combo,
            window.sort_label,
            window.sort_combo,
        )
        control_bounds = [
            (
                control.mapTo(central_widget, QPoint(0, 0)).x(),
                control.mapTo(
                    central_widget, QPoint(control.width(), 0)
                ).x(),
            )
            for control in controls
        ]

        self.assertLessEqual(window.minimumSizeHint().width(), window.minimumWidth())
        for left, right in control_bounds:
            self.assertGreaterEqual(left, controls_left)
            self.assertLessEqual(right, controls_right)
        for (_, current_right), (next_left, _) in zip(
            control_bounds, control_bounds[1:]
        ):
            self.assertLessEqual(current_right, next_left)

        max_filter_text_width = max(
            window.filter_combo.fontMetrics().horizontalAdvance(
                window.filter_combo.itemText(index)
            )
            for index in range(window.filter_combo.count())
        )
        self.assertLessEqual(
            window.filter_combo.width(),
            max_filter_text_width + 40,
        )
        self.assertEqual(
            window.sort_combo.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Expanding,
        )

        for palette in (LIGHT_THEME_COLORS, DARK_THEME_COLORS):
            with self.subTest(theme_background=palette.background):
                window._on_theme_changed(palette)
                self.app.processEvents()
                for combo in (window.filter_combo, window.sort_combo):
                    self._assert_combo_arrow_uses_color(
                        combo,
                        palette.text_primary,
                    )
                # grab() 会让 Qt 延迟刷新 sizeHint；重新稳定布局后再读取边界，
                # 避免把上一主题的几何与当前主题的箭头位置混在一起。
                self._settle_list_layout(window)
                theme_control_bounds = [
                    (
                        control.mapTo(central_widget, QPoint(0, 0)).x(),
                        control.mapTo(
                            central_widget, QPoint(control.width(), 0)
                        ).x(),
                    )
                    for control in controls
                ]
                for left, right in theme_control_bounds:
                    self.assertGreaterEqual(left, controls_left)
                    self.assertLessEqual(right, controls_right)

        option = QStyleOptionComboBox()
        option.initFrom(window.sort_combo)
        option.currentText = window.sort_combo.currentText()
        arrow_rect = window.sort_combo.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxArrow,
            window.sort_combo,
        )
        arrow_left = window.sort_combo.mapTo(
            central_widget, arrow_rect.topLeft()
        ).x()
        arrow_right = window.sort_combo.mapTo(
            central_widget, arrow_rect.bottomRight()
        ).x()
        self.assertGreaterEqual(arrow_left, control_bounds[-1][0])
        self.assertLessEqual(arrow_right, controls_right)

        narrow_option = QStyleOptionComboBox()
        window.sort_combo.initStyleOption(narrow_option)
        self.assertTrue(narrow_option.currentText.endswith("…"))
        self.assertNotEqual(
            narrow_option.currentText,
            window.sort_combo.currentText(),
        )
        self.assertEqual(
            [
                window.sort_combo.itemText(index)
                for index in range(window.sort_combo.count())
            ],
            [
                "创建时间 (新->旧)",
                "创建时间 (旧->新)",
                "截止日期 (近->远)",
                "截止日期 (远->近)",
                "优先级 (高->低)",
            ],
        )

        window.resize(500, 640)
        self._settle_list_layout(window)
        wide_option = QStyleOptionComboBox()
        window.sort_combo.initStyleOption(wide_option)
        self.assertEqual(wide_option.currentText, window.sort_combo.currentText())

    def test_vertical_scrollbar_is_compact_and_right_aligned(self) -> None:
        window = self._create_window(todo_count=10)
        window.resize(320, 640)
        window.show()
        self.app.processEvents()

        scrollbar = window.list_widget.verticalScrollBar()
        central_widget = window.centralWidget()

        self.assertTrue(scrollbar.isVisible())
        self.assertEqual(scrollbar.width(), 8)
        self.assertEqual(
            scrollbar.mapTo(
                window.list_widget, QPoint(scrollbar.width(), 0)
            ).x()
            - 1,
            window.list_widget.contentsRect().right(),
        )

        list_left = window.list_widget.mapTo(central_widget, QPoint(0, 0)).x()
        scrollbar_right = scrollbar.mapTo(
            central_widget, QPoint(scrollbar.width(), 0)
        ).x()
        scrollbar_right_spacing = central_widget.width() - scrollbar_right
        self.assertEqual(scrollbar_right_spacing, 7)
        self.assertEqual(
            list_left,
            scrollbar.width() + scrollbar_right_spacing,
        )

        add_button_right = window.add_button.mapTo(
            central_widget, QPoint(window.add_button.width(), 0)
        ).x()
        self.assertEqual(
            list_left,
            central_widget.width() - add_button_right,
        )

        item = window.list_widget.item(0)
        card = window.list_widget.itemWidget(item)
        left_margin, right_margin = self._card_outer_margins(window)
        self.assertLessEqual(abs(left_margin - right_margin), 1)
        self.assertLessEqual(card.width(), window.list_widget.viewport().width())
        self.assertEqual(
            window.list_widget.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )

    @classmethod
    def _settle_list_layout(cls, window: ModernTodoAppWindow) -> None:
        central_widget = window.centralWidget()
        central_layout = central_widget.layout()
        previous_geometry = None
        for _ in range(5):
            cls.app.processEvents()
            central_layout.invalidate()
            central_layout.activate()
            window.list_widget.doItemsLayout()
            cls.app.processEvents()
            current_geometry = tuple(
                child.geometry().getRect()
                for child in central_widget.findChildren(QWidget)
            )
            if current_geometry == previous_geometry:
                break
            previous_geometry = current_geometry

    @staticmethod
    def _card_heights(window: ModernTodoAppWindow) -> list[int]:
        return [
            window.list_widget.itemWidget(window.list_widget.item(index)).height()
            for index in range(window.list_widget.count())
        ]

    def _assert_card_gaps(self, window: ModernTodoAppWindow) -> None:
        for index in range(window.list_widget.count() - 1):
            current = window.list_widget.itemWidget(window.list_widget.item(index))
            following = window.list_widget.itemWidget(window.list_widget.item(index + 1))
            self.assertEqual(
                following.geometry().top() - current.geometry().bottom() - 1,
                8,
            )

    @staticmethod
    def _card_outer_margins(
        window: ModernTodoAppWindow,
        index: int = 0,
    ) -> tuple[int, int]:
        item = window.list_widget.item(index)
        card = window.list_widget.itemWidget(item)
        central_widget = window.centralWidget()
        left_margin = card.mapTo(central_widget, QPoint(0, 0)).x()
        right_margin = central_widget.width() - card.mapTo(
            central_widget, QPoint(card.width(), 0)
        ).x()
        return left_margin, right_margin

    def _assert_combo_arrow_uses_color(
        self,
        combo,
        expected_color: str,
    ) -> None:
        option = QStyleOptionComboBox()
        combo.initStyleOption(option)
        arrow_rect = combo.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxArrow,
            combo,
        )
        pixmap = combo.grab()
        image = pixmap.toImage()
        device_pixel_ratio = pixmap.devicePixelRatio()
        expected = QColor(expected_color)

        def is_expected_arrow_pixel(x: int, y: int) -> bool:
            pixel = image.pixelColor(
                min(int(x * device_pixel_ratio), image.width() - 1),
                min(int(y * device_pixel_ratio), image.height() - 1),
            )
            return max(
                abs(pixel.red() - expected.red()),
                abs(pixel.green() - expected.green()),
                abs(pixel.blue() - expected.blue()),
            ) <= 24

        self.assertTrue(
            any(
                is_expected_arrow_pixel(x, y)
                for y in range(arrow_rect.top(), arrow_rect.bottom() + 1)
                for x in range(arrow_rect.left(), arrow_rect.right() + 1)
            )
        )

    def _create_window(
        self,
        todo_count: int = 1,
        *,
        todos: list[dict] | None = None,
    ) -> ModernTodoAppWindow:
        if todos is None:
            todo = {
                "id": 1,
                "text": "这是一段很长很长的任务文字，用于检查窄窗口下的显示效果",
                "priority": "中",
                "completed": False,
                "dueDate": (
                    datetime.now(timezone.utc) + timedelta(days=123)
                ).isoformat(),
                "createdAt": "2026-07-17T00:00:00+00:00",
                "snoozeUntil": None,
            }
            todos = [{**todo, "id": index + 1} for index in range(todo_count)]
        load_patcher = patch("todo_app.main_window.load_todos", return_value=todos)
        load_patcher.start()
        self.addCleanup(load_patcher.stop)
        window = ModernTodoAppWindow()
        window.master_timer.stop()
        self.addCleanup(self._close_window, window)
        return window

    @staticmethod
    def _close_window(window: ModernTodoAppWindow) -> None:
        window.master_timer.stop()
        window._quitting_app = True
        window.tray_icon.hide()
        window.close()


if __name__ == "__main__":
    unittest.main()
