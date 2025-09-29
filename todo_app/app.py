"""应用程序入口函数。"""
from __future__ import annotations

import sys

from PySide6.QtCore import QMessageLogContext, QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from .constants import APP_ICON_PATH, APP_NAME, APP_VERSION
from .main_window import ModernTodoAppWindow
from .utils import get_icon


_original_qt_message_handler = None


def _filter_qt_messages(mode: QtMsgType, context: QMessageLogContext, message: str) -> None:
    """过滤掉特定的第三方底层警告，避免干扰日志。"""

    if "libpng warning: iCCP: known incorrect sRGB profile" in message:
        return

    if _original_qt_message_handler is not None:
        _original_qt_message_handler(mode, context, message)
    else:
        sys.stderr.write(f"{message}\n")


_original_qt_message_handler = qInstallMessageHandler(_filter_qt_messages)


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
