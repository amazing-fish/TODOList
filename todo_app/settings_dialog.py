"""轻量设置与运维对话框。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .constants import APP_ICON_PATH
from .theme import ThemeColors, ThemePreference, get_theme_manager
from .utils import get_icon


class SettingsDialog(QDialog):
    """集中管理主题、提示音/勿扰、开机自启与数据维护。"""

    theme_preference_changed = Signal(str)
    sound_enabled_changed = Signal(bool)
    dnd_toggled = Signal(bool)
    dnd_one_hour_requested = Signal()
    autostart_toggled = Signal(bool)
    clear_completed_requested = Signal()
    export_todos_requested = Signal()
    import_todos_requested = Signal()
    open_storage_dir_requested = Signal()

    def __init__(
        self,
        *,
        theme_preference: ThemePreference = ThemePreference.SYSTEM,
        sound_enabled: bool = True,
        dnd_enabled: bool = False,
        dnd_status_text: str = "未开启",
        autostart_supported: bool = False,
        autostart_enabled: bool = False,
        completed_count: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self._theme_manager = get_theme_manager()
        self._palette: ThemeColors = self._theme_manager.current_palette
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self._build_ui(
            theme_preference=theme_preference,
            sound_enabled=sound_enabled,
            dnd_enabled=dnd_enabled,
            dnd_status_text=dnd_status_text,
            autostart_supported=autostart_supported,
            autostart_enabled=autostart_enabled,
            completed_count=completed_count,
        )
        self._apply_palette(self._palette)

    def _build_ui(
        self,
        *,
        theme_preference: ThemePreference,
        sound_enabled: bool,
        dnd_enabled: bool,
        dnd_status_text: str,
        autostart_supported: bool,
        autostart_enabled: bool,
        completed_count: int,
    ) -> None:
        self.setWindowTitle("设置与工具")
        self.setWindowIcon(get_icon(APP_ICON_PATH, "S"))
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        appearance_group = QGroupBox("外观与启动")
        appearance_layout = QVBoxLayout(appearance_group)
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("主题模式:"))
        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("settingsThemeCombo")
        self.theme_combo.addItem("跟随系统", ThemePreference.SYSTEM.value)
        self.theme_combo.addItem("浅色模式", ThemePreference.LIGHT.value)
        self.theme_combo.addItem("深色模式", ThemePreference.DARK.value)
        index = self.theme_combo.findData(ThemePreference.coerce(theme_preference).value)
        self.theme_combo.setCurrentIndex(max(index, 0))
        self.theme_combo.currentIndexChanged.connect(self._emit_theme_changed)
        theme_row.addWidget(self.theme_combo, 1)
        appearance_layout.addLayout(theme_row)

        self.autostart_checkbox = QCheckBox("开机自动启动")
        self.autostart_checkbox.setObjectName("settingsAutostartCheckbox")
        self.autostart_checkbox.setEnabled(autostart_supported)
        self.autostart_checkbox.setChecked(autostart_supported and autostart_enabled)
        if not autostart_supported:
            self.autostart_checkbox.setToolTip("当前系统环境不支持自动写入 Windows 启动项")
        self.autostart_checkbox.toggled.connect(self.autostart_toggled.emit)
        appearance_layout.addWidget(self.autostart_checkbox)
        layout.addWidget(appearance_group)

        notify_group = QGroupBox("提醒与勿扰")
        notify_layout = QVBoxLayout(notify_group)
        self.sound_checkbox = QCheckBox("启用提醒与到期提示音")
        self.sound_checkbox.setObjectName("settingsSoundCheckbox")
        self.sound_checkbox.setChecked(sound_enabled)
        self.sound_checkbox.toggled.connect(self.sound_enabled_changed.emit)
        notify_layout.addWidget(self.sound_checkbox)

        dnd_row = QHBoxLayout()
        self.dnd_checkbox = QCheckBox("勿扰模式（暂不弹窗且静音）")
        self.dnd_checkbox.setObjectName("settingsDndCheckbox")
        self.dnd_checkbox.setChecked(dnd_enabled)
        self.dnd_checkbox.toggled.connect(self.dnd_toggled.emit)
        self.dnd_1h_button = QPushButton("勿扰 1 小时")
        self.dnd_1h_button.setObjectName("settingsDndOneHourButton")
        self.dnd_1h_button.clicked.connect(self._on_dnd_one_hour_clicked)
        dnd_row.addWidget(self.dnd_checkbox, 1)
        dnd_row.addWidget(self.dnd_1h_button)
        notify_layout.addLayout(dnd_row)

        self.dnd_status_label = QLabel(f"当前勿扰状态：{dnd_status_text}")
        self.dnd_status_label.setObjectName("settingsDndStatusLabel")
        notify_layout.addWidget(self.dnd_status_label)
        layout.addWidget(notify_group)

        data_group = QGroupBox("数据维护")
        data_layout = QVBoxLayout(data_group)
        row_a = QHBoxLayout()
        self.clear_completed_button = QPushButton(f"清理已完成 ({completed_count})")
        self.clear_completed_button.setObjectName("settingsClearCompletedButton")
        self.clear_completed_button.setEnabled(completed_count > 0)
        self.clear_completed_button.clicked.connect(self.clear_completed_requested.emit)
        self.open_dir_button = QPushButton("打开数据与日志目录")
        self.open_dir_button.setObjectName("settingsOpenDirButton")
        self.open_dir_button.clicked.connect(self.open_storage_dir_requested.emit)
        row_a.addWidget(self.clear_completed_button)
        row_a.addWidget(self.open_dir_button)
        data_layout.addLayout(row_a)

        row_b = QHBoxLayout()
        self.export_button = QPushButton("导出数据 (JSON)...")
        self.export_button.setObjectName("settingsExportButton")
        self.export_button.clicked.connect(self.export_todos_requested.emit)
        self.import_button = QPushButton("导入数据 (JSON)...")
        self.import_button.setObjectName("settingsImportButton")
        self.import_button.clicked.connect(self.import_todos_requested.emit)
        row_b.addWidget(self.export_button)
        row_b.addWidget(self.import_button)
        data_layout.addLayout(row_b)
        layout.addWidget(data_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _emit_theme_changed(self, _index: int) -> None:
        pref = self.theme_combo.currentData()
        if isinstance(pref, str):
            self.theme_preference_changed.emit(pref)

    def _on_dnd_one_hour_clicked(self) -> None:
        self.dnd_checkbox.blockSignals(True)
        self.dnd_checkbox.setChecked(True)
        self.dnd_checkbox.blockSignals(False)
        self.dnd_status_label.setText("当前勿扰状态：已开启（1小时后自动恢复）")
        self.dnd_one_hour_requested.emit()

    @Slot(ThemeColors)
    def _on_theme_changed(self, palette: ThemeColors) -> None:
        self._apply_palette(palette)

    def _apply_palette(self, palette: ThemeColors) -> None:
        self._palette = palette
        self.setStyleSheet(
            f"""
            QDialog {{ background-color: {palette.background}; color: {palette.text_primary}; }}
            QLabel, QCheckBox {{ color: {palette.text_primary}; font-size: 9.5pt; }}
            QGroupBox {{
                color: {palette.text_primary};
                border: 1px solid {palette.card_border};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }}
            QComboBox {{
                background-color: {palette.input_background};
                color: {palette.text_primary};
                border: 1px solid {palette.input_border};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QPushButton {{
                background-color: {palette.action_button_bg};
                color: {palette.text_primary};
                border: 1px solid {palette.action_button_border};
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 9pt;
            }}
            QPushButton:hover {{ border-color: {palette.accent}; }}
            QPushButton:disabled {{
                color: {palette.text_secondary};
                background-color: {palette.secondary_background};
            }}
            """
        )


__all__ = ["SettingsDialog"]
