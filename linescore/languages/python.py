"""Python language plugin."""

import ast

from linescore.models import FunctionInfo
from linescore.parsers.python import PythonParser


class PythonLanguage:
    """Python language support for all checks."""

    name = "python"
    suffixes = [".py"]
    ignore_dirs = {"__pycache__", ".mypy_cache", "__pypackages__", ".pytest_cache"}
    ignore_suffixes = {".pyc", ".pyo"}

    def __init__(self):
        self._parser = PythonParser()

    def extract_functions(self, source: str) -> list[FunctionInfo]:
        return self._parser.extract_functions(source)

    def extract_names(self, source: str) -> list[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        names = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
        return names
