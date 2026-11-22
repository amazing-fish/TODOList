"""单实例守护与唤醒通信。"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


logger = logging.getLogger(__name__)

_ACTIVATE_PAYLOAD = b"ACTIVATE\n"


def build_instance_server_name(storage_dir: Path) -> str:
    """根据持久化数据目录生成稳定的单实例本地服务名。"""

    digest = hashlib.sha256(str(storage_dir.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"TODOList-{digest}"


class SingleInstanceGuard(QObject):
    """基于 QLockFile + QLocalServer 的单实例互斥锁与外部启动唤醒。"""

    activate_requested = Signal()

    def __init__(
        self,
        server_name: str,
        parent: Optional[QObject] = None,
        *,
        lock_dir: Optional[Path] = None,
    ):
        super().__init__(parent)
        self._server_name = server_name
        self._lock_dir = lock_dir
        self._lock_file: Optional[QLockFile] = None
        self._server: Optional[QLocalServer] = None
        self._acquisition_error: Optional[str] = None

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def acquisition_error(self) -> Optional[str]:
        """当未能建立任何单实例互斥机制时返回错误描述，否则返回 None。"""

        return self._acquisition_error

    def _lock_path(self) -> Path:
        base_dir = self._lock_dir
        if base_dir is None:
            from .paths import RUNTIME_STORAGE_DIR

            base_dir = RUNTIME_STORAGE_DIR
        return base_dir / f".{self._server_name}.lock"

    def _probe_existing_instance(self, timeout_ms: int) -> bool:
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
            return True
        probe.deleteLater()
        return False

    def _listen_fallback_server(self) -> bool:
        """在确认无存活实例后，尝试通过本地服务提供互斥与唤醒保护。"""

        server = QLocalServer(self)
        if not server.listen(self._server_name):
            QLocalServer.removeServer(self._server_name)
            if not server.listen(self._server_name):
                error_detail = server.errorString() or "unknown listen failure"
                logger.error(
                    "单实例本地服务监听 %s 失败 (%s)，无法建立互斥保护",
                    self._server_name,
                    error_detail,
                )
                server.deleteLater()
                self._acquisition_error = error_detail
                return False

        server.newConnection.connect(self._handle_new_connection)
        self._server = server
        return True

    def try_acquire(self, timeout_ms: int = 500) -> bool:
        """尝试获取单实例锁；若已有实例运行则发送唤醒指令并返回 False。"""

        self._acquisition_error = None
        if self._lock_file is not None or self._server is not None:
            return True

        lock_path = self._lock_path()
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            if self._probe_existing_instance(timeout_ms):
                return False
            logger.warning("创建单实例锁目录失败 (%s)，尝试回退为本地服务串行化", exc)
            if self._listen_fallback_server():
                return True
            self._acquisition_error = f"{exc}; {self._acquisition_error or ''}".strip("; ")
            return False

        lock = QLockFile(str(lock_path))
        lock.setStaleLockTime(0)
        if not lock.tryLock(timeout_ms):
            lock_error = lock.error()
            if lock_error == QLockFile.LockError.LockFailedError:
                self._probe_existing_instance(timeout_ms)
                return False
            if self._probe_existing_instance(timeout_ms):
                return False
            logger.warning(
                "单实例文件锁 %s 创建失败 (%s)，回退为仅通过本地服务串行化",
                lock_path,
                lock_error,
            )
            return self._listen_fallback_server()

        server = QLocalServer(self)
        if not server.listen(self._server_name):
            QLocalServer.removeServer(self._server_name)
            if not server.listen(self._server_name):
                logger.warning(
                    "单实例监听 %s 失败 (%s)，将仅依赖目录文件锁运行",
                    self._server_name,
                    server.errorString(),
                )
                server.deleteLater()
                self._lock_file = lock
                return True

        server.newConnection.connect(self._handle_new_connection)
        self._lock_file = lock
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
        """关闭本地监听并释放文件互斥锁。"""

        try:
            if self._server is not None:
                self._server.close()
                self._server.deleteLater()
                self._server = None
        finally:
            if self._lock_file is not None:
                if self._lock_file.isLocked():
                    self._lock_file.unlock()
                self._lock_file = None


__all__ = ["SingleInstanceGuard", "build_instance_server_name"]
