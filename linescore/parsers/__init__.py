from typing import Protocol

from linescore.models import FunctionInfo


class Parser(Protocol):
    """Extracts functions and their statements from source code."""

    def extract_functions(self, source: str) -> list[FunctionInfo]:
        """Parse source code and return a list of functions with their statements.

        The `name` field of each FunctionInfo is what the judge will see.
        The parser decides what information to include in the name
        (e.g. just the name for Python, full signature for Java).
        """
        ...
