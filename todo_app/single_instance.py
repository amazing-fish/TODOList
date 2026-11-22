"""单实例守护与唤醒通信。"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


logger = logging.getLogger(__name__)

_ACTIVATE_PAYLOAD = b"ACTIVATE\n"


def build_instance_server_name(storage_dir: Path) -> str:
    """根据持久化数据目录生成稳定的单实例本地服务名。"""

    digest = hashlib.sha256(str(storage_dir.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"TODOList-{digest}"


class SingleInstanceGuard(QObject):
    """基于 QLocalServer 的单实例互斥锁与外部启动唤醒。"""

    activate_requested = Signal()

    def __init__(self, server_name: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._server_name = server_name
        self._server: Optional[QLocalServer] = None

    @property
    def server_name(self) -> str:
        return self._server_name

    def try_acquire(self, timeout_ms: int = 500) -> bool:
        """尝试获取单实例锁；若已有实例运行则发送唤醒指令并返回 False。"""

        probe = QLocalSocket(self)
        probe.connectToServer(self._server_name)
        if probe.waitForConnected(timeout_ms):
            try:
                probe.write(_ACTIVATE_PAYLOAD)
                probe.flush()
                probe.waitForBytesWritten(timeout_ms)
            finally:
                probe.disconnectFromServer()
                probe.deleteLater()
            return False
        probe.deleteLater()

        server = QLocalServer(self)
        if not server.listen(self._server_name):
            QLocalServer.removeServer(self._server_name)
            if not server.listen(self._server_name):
                logger.warning(
                    "单实例监听 %s 失败 (%s)，将允许独立启动",
                    self._server_name,
                    server.errorString(),
                )
                server.deleteLater()
                return True

        server.newConnection.connect(self._handle_new_connection)
        self._server = server
        return True

    def _handle_new_connection(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is None:
                continue
            client.waitForReadyRead(100)
            payload = bytes(client.readAll())
            client.disconnectFromServer()
            client.deleteLater()
            if not payload or b"ACTIVATE" in payload:
                self.activate_requested.emit()

    def release(self) -> None:
        """关闭本地监听并清理服务端名称。"""

        if self._server is None:
            return
        try:
            self._server.close()
            self._server.deleteLater()
        finally:
            self._server = None
            QLocalServer.removeServer(self._server_name)


__all__ = ["SingleInstanceGuard", "build_instance_server_name"]
