"""Windows 开机自启注册表管理与可测抽象。"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

AUTOSTART_RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = "TODOListDesktop"


class RegistryBackend(Protocol):
    """抽象开机自启注册表读写后端，便于单元测试隔离真实系统注册表。"""

    def is_supported(self) -> bool: ...

    def read_run_entry(self, name: str) -> str | None: ...

    def write_run_entry(self, name: str, command: str) -> None: ...

    def delete_run_entry(self, name: str) -> None: ...


class WindowsRegistryBackend:
    """基于 winreg HKCU Run 的真实开机自启实现。"""

    def is_supported(self) -> bool:
        return sys.platform.startswith("win")

    def read_run_entry(self, name: str) -> str | None:
        if not self.is_supported():
            return None
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                AUTOSTART_RUN_SUBKEY,
                0,
                winreg.KEY_READ,
            ) as key:
                value, _reg_type = winreg.QueryValueEx(key, name)
                return str(value) if value else None
        except FileNotFoundError:
            return None

    def write_run_entry(self, name: str, command: str) -> None:
        if not self.is_supported():
            raise RuntimeError("当前平台不支持 Windows 开机自启注册表")
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            AUTOSTART_RUN_SUBKEY,
            0,
            winreg.KEY_WRITE,
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)

    def delete_run_entry(self, name: str) -> None:
        if not self.is_supported():
            return
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                AUTOSTART_RUN_SUBKEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            return


def build_autostart_command(
    *,
    executable: str | None = None,
    entry_script: Path | None = None,
    frozen: bool | None = None,
) -> str:
    """构建开机自启启动命令行。"""

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    exe = Path(executable or sys.executable).resolve()
    if is_frozen:
        return f'"{exe}"'
    script = (entry_script or Path(__file__).resolve().parent.parent / "main.py").resolve()
    return f'"{exe}" "{script}"'


def is_autostart_supported(backend: RegistryBackend | None = None) -> bool:
    resolved = backend or WindowsRegistryBackend()
    return bool(resolved.is_supported())


def is_autostart_enabled(backend: RegistryBackend | None = None) -> bool:
    resolved = backend or WindowsRegistryBackend()
    if not resolved.is_supported():
        return False
    try:
        return bool(resolved.read_run_entry(AUTOSTART_VALUE_NAME))
    except OSError as exc:
        logger.warning("读取开机自启配置失败: %s", exc)
        return False


def set_autostart_enabled(
    enabled: bool,
    *,
    backend: RegistryBackend | None = None,
    command: str | None = None,
) -> bool:
    resolved = backend or WindowsRegistryBackend()
    if not resolved.is_supported():
        return False
    if enabled:
        resolved.write_run_entry(AUTOSTART_VALUE_NAME, command or build_autostart_command())
        return True
    resolved.delete_run_entry(AUTOSTART_VALUE_NAME)
    return False


__all__ = [
    "AUTOSTART_RUN_SUBKEY",
    "AUTOSTART_VALUE_NAME",
    "RegistryBackend",
    "WindowsRegistryBackend",
    "build_autostart_command",
    "is_autostart_enabled",
    "is_autostart_supported",
    "set_autostart_enabled",
]
