import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _extract_run_blocks(workflow_text: str) -> list[str]:
    """按 YAML 缩进规则提取每个 `run: |` 块，避免依赖第三方 YAML 库。"""

    lines = workflow_text.splitlines()
    blocks: list[str] = []
    idx = 0
    while idx < len(lines):
        match = re.match(r"^(\s*)run:\s*\|\s*$", lines[idx])
        if not match:
            idx += 1
            continue
        run_indent = len(match.group(1))
        idx += 1
        current_lines: list[str] = []
        while idx < len(lines):
            line = lines[idx]
            if not line.strip():
                current_lines.append(line)
                idx += 1
                continue
            line_indent = len(line) - len(line.lstrip(" "))
            if line_indent <= run_indent:
                break
            current_lines.append(line)
            idx += 1
        blocks.append("\n".join(current_lines))
    return blocks


class BuildWorkflowGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requirements_dev = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.build_workflow = (REPO_ROOT / ".github" / "workflows" / "build-exe.yml").read_text(
            encoding="utf-8"
        )
        constants_text = (REPO_ROOT / "todo_app" / "constants.py").read_text(encoding="utf-8")
        match = re.search(r'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"', constants_text)
        assert match is not None
        self.app_version = match.group(1)

    def test_requirements_dev_pins_pyinstaller_closure(self) -> None:
        for expected_pin in (
            "PyInstaller==6.21.0",
            "altgraph==0.17.5",
            "packaging==26.3",
            "pefile==2024.8.26",
            "pyinstaller-hooks-contrib==2026.10",
            "pywin32-ctypes==0.2.3",
        ):
            self.assertIn(expected_pin, self.requirements_dev)

    def test_build_workflow_uses_safe_concurrency_and_manual_recovery_inputs(self) -> None:
        self.assertNotIn("pip install --upgrade pip", self.build_workflow)
        self.assertIn("build-exe-main-preview-build", self.build_workflow)
        self.assertIn("build-exe-release-publish", self.build_workflow)
        self.assertIn("cancel-in-progress: false", self.build_workflow)
        self.assertIn("persist-credentials: false", self.build_workflow)
        self.assertIn("refs/tags/{0}", self.build_workflow)
        self.assertIn("git rev-parse HEAD", self.build_workflow)
        self.assertIn("release_tag:", self.build_workflow)
        self.assertIn("confirm_release_tag:", self.build_workflow)
        self.assertIn("publish_release:", self.build_workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", self.build_workflow)
        self.assertIn("SHA256", self.build_workflow)
        self.assertIn("overwrite_files: true", self.build_workflow)
        self.assertIn("INPUT_RELEASE_TAG: ${{ inputs.release_tag }}", self.build_workflow)
        self.assertIn('--add-data "assets;assets"', self.build_workflow)

        run_blocks = _extract_run_blocks(self.build_workflow)
        self.assertTrue(run_blocks)
        for block in run_blocks:
            self.assertNotIn("${{ inputs.", block)
            self.assertNotIn("${{ github.ref_name", block)
            self.assertNotIn("${{ steps.", block)
            self.assertNotIn("${{ needs.", block)

    def test_tag_validation_runs_before_pip_install(self) -> None:
        validate_idx = self.build_workflow.index("校验版本与生成构建计划")
        install_idx = self.build_workflow.index("python -m pip install -r requirements-dev.txt")
        self.assertLess(validate_idx, install_idx)
        self.assertRegex(self.app_version, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
