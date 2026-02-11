"""Tests for the name-to-file check."""

import tempfile
from pathlib import Path

from linescore.checks.name_to_file import NameToFileCheck
from linescore.languages.python import PythonLanguage


class TestNameToFileCheck:
    def setup_method(self):
        self.check = NameToFileCheck(PythonLanguage())

    def test_extracts_tasks_from_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "math_utils.py").write_text("def add(a, b): return a + b\ndef subtract(a, b): return a - b\n")
            (Path(tmp) / "string_utils.py").write_text("def upper(s): return s.upper()\nclass Formatter: pass\n")

            tasks = self.check.extract(tmp)

        assert len(tasks) == 4
        files = {t.actual for t in tasks}
        assert files == {"math_utils.py", "string_utils.py"}
        items = {t.item for t in tasks}
        assert "add" in items
        assert "Formatter" in items

    def test_too_few_files_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "only.py").write_text("def foo(): pass\n")
            assert self.check.extract(tmp) == []

    def test_nonexistent_path_returns_empty(self):
        assert self.check.extract("/nonexistent/path") == []

    def test_build_prompt(self):
        prompt = self.check.build_prompt(["auth.py", "db.py"], "connect")
        assert "auth.py" in prompt
        assert "db.py" in prompt
        assert "connect" in prompt
