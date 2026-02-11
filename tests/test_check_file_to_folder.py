"""Tests for the file-to-folder check."""

import tempfile
from pathlib import Path

from linescore.checks.file_to_folder import FileToFolderCheck


class TestFileToFolderCheck:
    def setup_method(self):
        self.check = FileToFolderCheck()

    def test_extracts_tasks_from_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create two subdirs with files
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("")
            (root / "src" / "utils.py").write_text("")
            (root / "tests").mkdir()
            (root / "tests" / "test_main.py").write_text("")
            (root / "tests" / "test_utils.py").write_text("")

            tasks = self.check.extract(tmp)

        assert len(tasks) > 0
        # Should have tasks from root (src, tests dirs) + from src/ + from tests/
        folders = {t.actual for t in tasks}
        assert len(folders) >= 2

    def test_skips_hidden_and_pycache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("")
            (root / "src" / "utils.py").write_text("")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("")
            (root / "tests").mkdir()
            (root / "tests" / "test_a.py").write_text("")
            (root / "tests" / "test_b.py").write_text("")

            tasks = self.check.extract(tmp)

        items = {t.item for t in tasks}
        assert ".git" not in items

    def test_too_few_folders_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "only.py").write_text("")
            assert self.check.extract(tmp) == []

    def test_nonexistent_path_returns_empty(self):
        assert self.check.extract("/nonexistent/path") == []

    def test_build_prompt(self):
        prompt = self.check.build_prompt(["src", "tests", "docs"], "main.py")
        assert "src" in prompt
        assert "tests" in prompt
        assert "main.py" in prompt
