"""Check protocol — what to score."""

from typing import Protocol

from linescore.models import ClassificationTask


class Check(Protocol):
    """A scoring check: extracts classification tasks from a target."""

    name: str

    def extract(self, target: str) -> list[ClassificationTask]:
        """Extract items to classify from the target (source code, path, etc.)."""
        ...

    def build_prompt(self, candidates: list[str], item: str) -> str:
        """Build an LLM prompt asking it to classify `item` among `candidates`."""
        ...
