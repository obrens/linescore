"""Source code parsers — extract functions and statements from source code."""

from typing import Protocol

from linescore.models import FunctionInfo


class Parser(Protocol):
    """Extracts functions and their statements from source code.

    Implement this to add support for a new language.
    """

    def extract_functions(self, source: str) -> list[FunctionInfo]:
        """Parse source code and return a list of functions with their statements."""
        ...
