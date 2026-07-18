"""应用字体注册、回退与打包资源合同测试。"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


class ApplicationFontTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_bundled_harmony_font_registers_with_expected_family(self) -> None:
        from todo_app.constants import APP_FONT_FAMILY, APP_FONT_PATH
        from todo_app.fonts import register_application_font
        from todo_app.paths import resource_path

        font_path = resource_path(APP_FONT_PATH)
        self.assertTrue(font_path.is_file())
        self.assertEqual(register_application_font(font_path), APP_FONT_FAMILY)

    def test_missing_font_uses_safe_system_fallback(self) -> None:
        from todo_app.fonts import apply_application_font

        missing_path = Path("does-not-exist/HarmonyOS_Sans_SC_Regular.ttf")
        with patch("builtins.print") as warning:
            family = apply_application_font(missing_path)

        self.assertTrue(family)
        self.assertEqual(QApplication.font().family(), family)
        warning.assert_called_once()

    def test_font_and_license_are_covered_by_packaged_assets(self) -> None:
        from todo_app.constants import APP_FONT_LICENSE_PATH, APP_FONT_PATH
        from todo_app.paths import resource_path

        self.assertEqual(APP_FONT_PATH, "assets/fonts/HarmonyOS_Sans_SC_Regular.ttf")
        self.assertEqual(APP_FONT_LICENSE_PATH, "assets/fonts/LICENSE_HarmonyOS_Sans.txt")
        self.assertTrue(resource_path(APP_FONT_PATH).is_file())
        self.assertTrue(resource_path(APP_FONT_LICENSE_PATH).is_file())
        workflow = resource_path(".github/workflows/build-exe.yml").read_text(encoding="utf-8")
        self.assertIn('--add-data "assets;assets"', workflow)

    def test_task_dialog_inherits_registered_font_family(self) -> None:
        from todo_app.constants import APP_FONT_FAMILY
        from todo_app.dialogs import TaskEditDialog
        from todo_app.fonts import apply_application_font

        self.assertEqual(apply_application_font(), APP_FONT_FAMILY)
        dialog = TaskEditDialog()
        self.addCleanup(dialog.close)

        representative_widgets = (
            dialog.task_input,
            dialog.priority_combo,
            dialog.reminder_combo,
            dialog.time_edit,
            dialog.date_edit,
            dialog.button_box,
        )
        for widget in representative_widgets:
            with self.subTest(widget=type(widget).__name__):
                self.assertEqual(widget.font().family(), APP_FONT_FAMILY)

    def test_startup_applies_font_before_creating_window(self) -> None:
        from todo_app import app as app_module

        events: list[str] = []
        fake_app = MagicMock()
        fake_app.exec.return_value = 0
        fake_window = MagicMock()
        app_class = MagicMock()
        app_class.instance.return_value = fake_app

        with (
            patch.object(app_module, "QApplication", app_class),
            patch.object(
                app_module,
                "apply_application_font",
                side_effect=lambda: events.append("font"),
                create=True,
            ),
            patch.object(
                app_module,
                "ModernTodoAppWindow",
                side_effect=lambda: (events.append("window"), fake_window)[1],
            ),
            self.assertRaises(SystemExit),
        ):
            app_module.run()

        self.assertEqual(events, ["font", "window"])


if __name__ == "__main__":
    unittest.main()
