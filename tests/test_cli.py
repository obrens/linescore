"""Tests for CLI target planning and discovery."""

import os
from pathlib import Path

from linescore.cli import _plan_runs, _find_dirs_with_sources, _count_loc, _dir_loc
from linescore.languages.python import PythonLanguage


def _make_tree(tmp_path: Path, structure: dict):
    """Create a directory tree from a nested dict. Values are file contents."""
    for name, content in structure.items():
        path = tmp_path / name
        if isinstance(content, dict):
            path.mkdir(exist_ok=True)
            _make_tree(path, content)
        else:
            path.write_text(content)


class TestFindDirsWithSources:
    def test_finds_dirs_with_two_plus_source_files(self, tmp_path):
        _make_tree(tmp_path, {
            "a.py": "x = 1",
            "b.py": "y = 2",
            "sub": {
                "c.py": "z = 3",
                "d.py": "w = 4",
            },
            "empty": {},
            "one_file": {"e.py": "v = 5"},
        })
        lang = PythonLanguage()
        dirs = _find_dirs_with_sources(tmp_path, lang)
        dir_names = [d.name for d in dirs]
        assert tmp_path.name in dir_names  # root has 2 .py files
        assert "sub" in dir_names
        assert "empty" not in dir_names
        assert "one_file" not in dir_names

    def test_skips_hidden_and_ignored_dirs(self, tmp_path):
        _make_tree(tmp_path, {
            ".hidden": {"a.py": "x = 1", "b.py": "y = 2"},
            "__pycache__": {"a.py": "x = 1", "b.py": "y = 2"},
            "ok": {"a.py": "x = 1", "b.py": "y = 2"},
        })
        lang = PythonLanguage()
        dirs = _find_dirs_with_sources(tmp_path, lang)
        dir_names = [d.name for d in dirs]
        assert "ok" in dir_names
        assert ".hidden" not in dir_names
        assert "__pycache__" not in dir_names


class TestPlanRuns:
    def test_single_file_only_line_to_function(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def foo(): pass")
        runs = _plan_runs([str(src)], "all", PythonLanguage())
        assert len(runs) == 1
        assert runs[0][0] == "line-to-function"
        assert runs[0][1] == str(src)

    def test_directory_runs_all_checks(self, tmp_path):
        _make_tree(tmp_path, {
            "a.py": "def foo(): pass",
            "b.py": "def bar(): pass",
            "sub": {
                "c.py": "def baz(): pass",
                "d.py": "def qux(): pass",
            },
        })
        lang = PythonLanguage()
        runs = _plan_runs([str(tmp_path)], "all", lang)
        check_names = [r[0] for r in runs]
        assert "line-to-function" in check_names
        assert "name-to-file" in check_names
        assert "file-to-folder" in check_names

    def test_specific_check_filters(self, tmp_path):
        _make_tree(tmp_path, {
            "a.py": "def foo(): pass",
            "b.py": "def bar(): pass",
        })
        lang = PythonLanguage()
        runs = _plan_runs([str(tmp_path)], "name-to-file", lang)
        assert all(r[0] == "name-to-file" for r in runs)

    def test_non_source_file_skipped(self, tmp_path):
        txt = tmp_path / "readme.txt"
        txt.write_text("hello")
        runs = _plan_runs([str(txt)], "all", PythonLanguage())
        assert runs == []

    def test_name_to_file_discovers_subdirs(self, tmp_path):
        _make_tree(tmp_path, {
            "a.py": "x = 1",
            "b.py": "y = 2",
            "pkg": {
                "c.py": "z = 3",
                "d.py": "w = 4",
            },
        })
        lang = PythonLanguage()
        runs = _plan_runs([str(tmp_path)], "name-to-file", lang)
        labels = [r[1] for r in runs]
        # Should find both root and pkg/
        assert str(tmp_path) in labels
        assert str(tmp_path / "pkg") in labels

    def test_runs_include_loc(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("line1\nline2\nline3\n")
        runs = _plan_runs([str(src)], "all", PythonLanguage())
        assert len(runs) == 1
        # 4th element is LoC
        assert runs[0][3] == 3

    def test_directory_loc_for_name_to_file(self, tmp_path):
        _make_tree(tmp_path, {
            "a.py": "x = 1\ny = 2",
            "b.py": "z = 3",
        })
        lang = PythonLanguage()
        runs = _plan_runs([str(tmp_path)], "name-to-file", lang)
        assert len(runs) == 1
        # a.py has 2 lines, b.py has 1 line = 3 total (non-recursive)
        assert runs[0][3] == 3


class TestCountLoc:
    def test_counts_file_lines(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("line1\nline2\nline3\n")
        assert _count_loc(f, PythonLanguage()) == 3

    def test_counts_directory_recursively(self, tmp_path):
        _make_tree(tmp_path, {
            "a.py": "x = 1\ny = 2",
            "sub": {"b.py": "z = 3"},
        })
        assert _count_loc(tmp_path, PythonLanguage()) == 3

    def test_skips_ignored_dirs(self, tmp_path):
        _make_tree(tmp_path, {
            "a.py": "x = 1",
            "__pycache__": {"cached.py": "big\nfile\nhere"},
        })
        assert _count_loc(tmp_path, PythonLanguage()) == 1


class TestDirLoc:
    def test_counts_only_immediate_files(self, tmp_path):
        _make_tree(tmp_path, {
            "a.py": "x = 1\ny = 2",
            "b.py": "z = 3",
            "sub": {"c.py": "w = 4\nv = 5\nu = 6"},
        })
        # Only a.py (2) + b.py (1) = 3, not sub/c.py
        assert _dir_loc(tmp_path, PythonLanguage()) == 3
