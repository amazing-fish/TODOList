"""内置提示音频资源与播放降级验证测试。"""
from __future__ import annotations

import os
import unittest
import wave
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from todo_app.constants import DUE_SOUND_PATH, REMINDER_SOUND_PATH  # noqa: E402
from todo_app.paths import resource_path  # noqa: E402
from todo_app.utils import play_sound_effect  # noqa: E402


class SoundAssetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_bundled_wav_assets_exist_and_are_valid_pcm(self) -> None:
        for rel_path in (REMINDER_SOUND_PATH, DUE_SOUND_PATH):
            with self.subTest(path=rel_path):
                resolved = resource_path(rel_path)
                self.assertTrue(resolved.is_file(), f"缺少音频文件: {resolved}")
                with wave.open(str(resolved), "rb") as wf:
                    self.assertEqual(wf.getnchannels(), 1)
                    self.assertEqual(wf.getsampwidth(), 2)
                    self.assertGreater(wf.getnframes(), 0)

    def test_play_sound_effect_loads_bundled_assets_without_beep_fallback(self) -> None:
        player = MagicMock()
        with patch.object(self.app, "beep") as beep_mock:
            play_sound_effect(player, REMINDER_SOUND_PATH)
            play_sound_effect(player, DUE_SOUND_PATH)

        self.assertEqual(player.setSource.call_count, 2)
        self.assertEqual(player.play.call_count, 2)
        beep_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
