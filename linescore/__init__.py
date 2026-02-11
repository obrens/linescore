"""linescore — code quality scoring via AI classification."""

from linescore.models import (
    ClassificationTask,
    ConfusedPair,
    FunctionInfo,
    CategoryScore,
    JudgmentResult,
    GuessResult,
    ScoreResult,
)
from linescore.scorer import score
from linescore.backends import Backend
from linescore.checks import Check
from linescore.languages import Language

__all__ = [
    "score",
    "Backend",
    "Check",
    "Language",
    "ClassificationTask",
    "FunctionInfo",
    "JudgmentResult",
    "GuessResult",
    "CategoryScore",
    "ConfusedPair",
    "ScoreResult",
]
