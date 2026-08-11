"""应用身份与持久化设置兼容性测试。"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, call, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from todo_app.constants import (  # noqa: E402
    APP_NAME,
    APP_VERSION,
    SETTINGS_APPLICATION,
    SETTINGS_ORGANIZATION,
)
from todo_app.main_window import ModernTodoAppWindow  # noqa: E402


class ApplicationIdentityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_visible_identity_targets_v2_without_changing_settings_namespace(self) -> None:
        self.assertEqual(APP_NAME, "桌面待办事项")
        self.assertEqual(APP_VERSION, "2.1.1")
        self.assertNotIn("v1", APP_NAME)
        self.assertEqual(SETTINGS_ORGANIZATION, "MyProductiveApp")
        self.assertEqual(SETTINGS_APPLICATION, "桌面待办事项 v1")

    def test_startup_uses_visible_identity_and_stable_organization(self) -> None:
        from todo_app import app as app_module

        fake_app = MagicMock()
        fake_app.exec.return_value = 0
        fake_window = MagicMock()
        app_class = MagicMock()
        app_class.instance.return_value = fake_app

        with (
            patch.object(app_module, "QApplication", app_class),
            patch.object(app_module, "apply_application_font"),
            patch.object(app_module, "get_icon"),
            patch.object(app_module, "ModernTodoAppWindow", return_value=fake_window),
            self.assertRaises(SystemExit),
        ):
            app_module.run()

        fake_app.setApplicationName.assert_called_once_with(APP_NAME)
        fake_app.setApplicationVersion.assert_called_once_with(APP_VERSION)
        fake_app.setOrganizationName.assert_called_once_with(SETTINGS_ORGANIZATION)

    def test_main_window_reads_legacy_settings_and_shows_current_identity(self) -> None:
        legacy_geometry = QByteArray(b"legacy-geometry")
        legacy_window_state = QByteArray(b"legacy-window-state")
        settings = MagicMock()
        settings.value.side_effect = [legacy_geometry, legacy_window_state]

        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.QSettings", return_value=settings) as settings_class,
            patch.object(
                ModernTodoAppWindow,
                "restoreGeometry",
                return_value=True,
            ) as restore_geometry,
            patch.object(
                ModernTodoAppWindow,
                "restoreState",
                return_value=True,
            ) as restore_state,
        ):
            window = ModernTodoAppWindow()

        window.master_timer.stop()
        self.addCleanup(self._close_window, window)

        settings_class.assert_called_once_with(
            SETTINGS_ORGANIZATION,
            SETTINGS_APPLICATION,
        )
        self.assertEqual(
            settings.value.call_args_list,
            [
                call("geometry"),
                call("windowState"),
            ],
        )
        restore_geometry.assert_called_once_with(legacy_geometry)
        restore_state.assert_called_once_with(legacy_window_state)
        self.assertEqual(window.windowTitle(), f"{APP_NAME} - v{APP_VERSION}")
        self.assertEqual(window.tray_icon.toolTip(), APP_NAME)

    @staticmethod
    def _close_window(window: ModernTodoAppWindow) -> None:
        window.master_timer.stop()
        window._quitting_app = True
        window.tray_icon.hide()
        window.close()


if __name__ == "__main__":
    unittest.main()
