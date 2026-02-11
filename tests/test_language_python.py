"""Tests for the Python language plugin."""

from linescore.languages.python import PythonLanguage


class TestPythonLanguage:
    def setup_method(self):
        self.lang = PythonLanguage()

    def test_name(self):
        assert self.lang.name == "python"

    def test_suffixes(self):
        assert ".py" in self.lang.suffixes

    def test_ignore_dirs(self):
        assert "__pycache__" in self.lang.ignore_dirs

    def test_ignore_suffixes(self):
        assert ".pyc" in self.lang.ignore_suffixes

    def test_extract_functions(self):
        source = "def foo():\n    x = 1\n    return x\ndef bar():\n    y = 2\n    return y\n"
        funcs = self.lang.extract_functions(source)
        names = [f.name for f in funcs]
        assert "foo" in names
        assert "bar" in names

    def test_extract_names(self):
        source = "def foo(): pass\nclass Bar: pass\nasync def baz(): pass\n"
        assert self.lang.extract_names(source) == ["foo", "Bar", "baz"]

    def test_extract_names_skips_nested(self):
        source = "def outer():\n    def inner(): pass\n"
        assert self.lang.extract_names(source) == ["outer"]

    def test_extract_names_syntax_error(self):
        assert self.lang.extract_names("def broken(") == []
