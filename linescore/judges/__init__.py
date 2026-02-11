from typing import Protocol

from linescore.models import JudgmentResult


class Judge(Protocol):
    """Asks an AI to guess which function a statement belongs to."""

    def judge(self, function_names: list[str], statement: str) -> JudgmentResult:
        """Given a list of function names and a single statement,
        return a guess for which function the statement belongs to."""
        ...
