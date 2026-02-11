"""Language protocol — all language-specific behavior in one place."""

from typing import Protocol

from linescore.models import FunctionInfo


class Language(Protocol):
    """Everything a check needs to know about a programming language.

    Implement this to add support for a new language.
    """

    name: str
    suffixes: list[str]
    ignore_dirs: set[str]
    ignore_suffixes: set[str]

    def extract_functions(self, source: str) -> list[FunctionInfo]:
        """Extract functions with statements from source code.
        Used by the line-to-function check."""
        ...

    def extract_names(self, source: str) -> list[str]:
        """Extract top-level function/class names from source code.
        Used by the name-to-file check."""
        ...
