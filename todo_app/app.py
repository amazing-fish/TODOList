"""应用程序入口函数。"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .constants import APP_NAME, APP_VERSION
from .main_window import ModernTodoAppWindow
from .utils import get_icon
from .constants import APP_ICON_PATH


def run() -> None:
    """启动桌面应用。"""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("MyProductiveApp")
    app.setWindowIcon(get_icon(APP_ICON_PATH, "TD"))
    app.setQuitOnLastWindowClosed(False)

    main_window = ModernTodoAppWindow()
    if main_window.isMinimized() or main_window.isHidden():
        main_window.showNormal()
    main_window.raise_()
    main_window.activateWindow()

    sys.exit(app.exec())


__all__ = ["run"]
