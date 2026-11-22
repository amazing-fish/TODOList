"""单实例守护与外部唤醒测试。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from todo_app import app as app_module  # noqa: E402
from todo_app.main_window import ModernTodoAppWindow  # noqa: E402
from todo_app.single_instance import SingleInstanceGuard, build_instance_server_name  # noqa: E402


class SingleInstanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_server_name_is_deterministic_and_isolated_per_storage_dir(self) -> None:
        with tempfile.TemporaryDirectory() as dir_a, tempfile.TemporaryDirectory() as dir_b:
            path_a = Path(dir_a)
            path_b = Path(dir_b)
            self.assertEqual(
                build_instance_server_name(path_a),
                build_instance_server_name(path_a),
            )
            self.assertNotEqual(
                build_instance_server_name(path_a),
                build_instance_server_name(path_b),
            )

    def test_second_instance_signals_primary_and_is_rejected(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_dir = Path(temp_dir.name)
        server_name = build_instance_server_name(lock_dir)
        primary = SingleInstanceGuard(server_name, lock_dir=lock_dir)
        secondary = SingleInstanceGuard(server_name, lock_dir=lock_dir)
        self.addCleanup(secondary.release)
        self.addCleanup(primary.release)

        activated: list[bool] = []
        primary.activate_requested.connect(lambda: activated.append(True))

        self.assertTrue(primary.try_acquire())
        self.assertFalse(secondary.try_acquire())
        self.app.processEvents()
        self.assertEqual(activated, [True])

    def test_run_exits_cleanly_when_another_instance_holds_lock(self) -> None:
        fake_app = MagicMock()
        fake_guard = MagicMock()
        fake_guard.try_acquire.return_value = False
        app_class = MagicMock()
        app_class.instance.return_value = fake_app

        with (
            patch.object(app_module, "QApplication", app_class),
            patch.object(app_module, "apply_application_font"),
            patch.object(app_module, "configure_logging"),
            patch.object(app_module, "SingleInstanceGuard", return_value=fake_guard),
            patch.object(app_module, "get_icon"),
            patch.object(app_module, "ModernTodoAppWindow") as window_cls,
        ):
            with self.assertRaises(SystemExit) as ctx:
                app_module.run()

        self.assertEqual(ctx.exception.code, 0)
        window_cls.assert_not_called()
        fake_app.exec.assert_not_called()

    def test_activate_from_external_launch_restores_hidden_window(self) -> None:
        with (
            patch("todo_app.main_window.load_todos", return_value=[]),
            patch("todo_app.main_window.QSettings", return_value=MagicMock()),
        ):
            window = ModernTodoAppWindow()
        window.master_timer.stop()
        self.addCleanup(self._close_window, window)

        window.hide()
        self.assertTrue(window.isHidden())
        window.activate_from_external_launch()
        self.assertTrue(window.isVisible())

    @staticmethod
    def _close_window(window: ModernTodoAppWindow) -> None:
        window._quitting_app = True
        window.tray_icon.hide()
        window.close()
        window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
