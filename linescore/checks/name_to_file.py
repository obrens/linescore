"""Check: can the LLM guess which file a function/class name belongs to?"""

import ast
from pathlib import Path
from typing import Callable

from linescore.models import ClassificationTask


_PROMPT_TEMPLATE = """\
You are a code analysis tool. You will be given:
1. A list of file names from a project.
2. A single function or class name from one of those files.

Your task: guess which file the name most likely belongs to.

Respond with ONLY a JSON object: {{"guess": "<filename>", "confidence": <0.0-1.0>}}
No other text.

Files in this directory:
{file_list}

Name:
  {name}

Which file does this name belong to?"""


def extract_python_names(source: str) -> list[str]:
    """Extract top-level function and class names from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    names = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


# Type for a function that extracts names from source code
NameExtractor = Callable[[str], list[str]]


class NameToFileCheck:
    """Score how identifiable each function/class name is within its file."""

    name = "name-to-file"

    def __init__(
        self,
        suffix: str = ".py",
        extract_names: NameExtractor = extract_python_names,
    ):
        self._suffix = suffix
        self._extract_names = extract_names

    def extract(self, target: str) -> list[ClassificationTask]:
        """Extract classification tasks from a directory of source files.

        Args:
            target: Path to a directory containing source files.
        """
        directory = Path(target)
        if not directory.is_dir():
            return []

        # Collect names per file
        file_names: dict[str, list[str]] = {}
        for src_file in sorted(directory.glob(f"*{self._suffix}")):
            try:
                source = src_file.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            names = self._extract_names(source)
            if names:
                file_names[src_file.name] = names

        if len(file_names) < 2:
            return []

        all_files = list(file_names.keys())
        tasks = []
        for filename, names in file_names.items():
            for name in names:
                tasks.append(ClassificationTask(
                    item=name,
                    actual=filename,
                    candidates=all_files,
                ))
        return tasks

    def build_prompt(self, candidates: list[str], item: str) -> str:
        file_list = "\n".join(f"  - {f}" for f in candidates)
        return _PROMPT_TEMPLATE.format(file_list=file_list, name=item)
