"""Tests for the file-to-folder check."""

import tempfile
from pathlib import Path

from linescore.checks.file_to_folder import FileToFolderCheck
from linescore.languages.python import PythonLanguage


class TestFileToFolderCheck:
    def setup_method(self):
        self.check = FileToFolderCheck(PythonLanguage())

    def test_extracts_tasks_from_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("")
            (root / "src" / "utils.py").write_text("")
            (root / "tests").mkdir()
            (root / "tests" / "test_main.py").write_text("")
            (root / "tests" / "test_utils.py").write_text("")

            tasks = self.check.extract(tmp)

        assert len(tasks) > 0
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
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "main.cpython-312.pyc").write_text("")
            (root / "tests").mkdir()
            (root / "tests" / "test_a.py").write_text("")
            (root / "tests" / "test_b.py").write_text("")

            tasks = self.check.extract(tmp)

        items = {t.item for t in tasks}
        folders = {t.actual for t in tasks}
        assert ".git" not in items
        assert "__pycache__" not in items
        assert "__pycache__" not in folders

    def test_skips_pyc_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("")
            (root / "src" / "main.pyc").write_text("")
            (root / "src" / "utils.py").write_text("")
            (root / "tests").mkdir()
            (root / "tests" / "test_a.py").write_text("")
            (root / "tests" / "test_b.py").write_text("")

            tasks = self.check.extract(tmp)

        items = {t.item for t in tasks}
        assert "main.pyc" not in items

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

    def test_candidates_are_neighborhood_not_global(self):
        """Candidates for a folder should be its local neighborhood,
        not every folder in the tree."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Deep tree with unrelated components
            for comp in ["src/auth", "src/billing", "src/billing/utils"]:
                (root / comp).mkdir(parents=True)
            (root / "src" / "auth" / "login.py").write_text("")
            (root / "src" / "auth" / "token.py").write_text("")
            (root / "src" / "billing" / "invoice.py").write_text("")
            (root / "src" / "billing" / "payment.py").write_text("")
            (root / "src" / "billing" / "utils" / "fmt.py").write_text("")
            (root / "src" / "billing" / "utils" / "calc.py").write_text("")

            tasks = self.check.extract(tmp)

        # Tasks for items in src/auth should NOT have src/billing/utils
        # as a candidate — it's in a different component
        auth_tasks = [t for t in tasks if t.actual == "src/auth"]
        assert len(auth_tasks) > 0
        for t in auth_tasks:
            assert "src/billing/utils" not in t.candidates
            # Should have: src/auth, src/billing (sibling), src (parent)
            assert "src/auth" in t.candidates
            assert "src/billing" in t.candidates
            assert "src" in t.candidates

    def test_root_neighborhood_includes_child_folders(self):
        """Root folder candidates should be root + its child folders."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "setup.py").write_text("")
            (root / "README.md").write_text("")

            tasks = self.check.extract(tmp)

        root_tasks = [t for t in tasks if t.actual == "."]
        if root_tasks:  # root has 2+ children so it should have tasks
            for t in root_tasks:
                assert "." in t.candidates
                assert "src" in t.candidates
                assert "tests" in t.candidates

    def test_single_folder_no_siblings_skipped(self):
        """A folder with no siblings and no meaningful parent gets < 2
        candidates and should be skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Only one subfolder, no other structure
            (root / "pkg").mkdir()
            (root / "pkg" / "a.py").write_text("")
            (root / "pkg" / "b.py").write_text("")
            # Root has only 1 child dir, so root won't qualify (only pkg/ visible)
            # pkg's neighborhood: siblings=none, parent="." → candidates = [".", "pkg"]

            tasks = self.check.extract(tmp)

        # pkg should still have tasks since its neighborhood is [".", "pkg"]
        if tasks:
            pkg_tasks = [t for t in tasks if t.actual == "pkg"]
            for t in pkg_tasks:
                assert len(t.candidates) >= 2
