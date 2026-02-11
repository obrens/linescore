from dataclasses import dataclass, field


@dataclass
class FunctionInfo:
    """A function extracted from source code, with its statements."""
    name: str
    statements: list[str] = field(default_factory=list)


@dataclass
class JudgmentResult:
    """The AI's guess for which function a statement belongs to."""
    guess: str
    confidence: float


@dataclass
class ClassificationTask:
    """A single item to classify: what it is, the correct answer, and all options."""
    item: str
    actual: str
    candidates: list[str]


@dataclass
class GuessResult:
    """Result of judging a single item."""
    statement: str
    actual_function: str
    guessed_function: str
    confidence: float
    correct: bool


@dataclass
class CategoryScore:
    """Score breakdown for a single category (function, file, or folder)."""
    name: str
    total: int
    correct: int
    score: float
    results: list[GuessResult] = field(default_factory=list)


@dataclass
class ConfusedPair:
    """Two categories whose items get confused with each other."""
    function_a: str
    function_b: str
    count: int


@dataclass
class ScoreResult:
    """Complete scoring result."""
    score: float
    total: int
    correct: int
    check: str = ""
    function_scores: list[CategoryScore] = field(default_factory=list)
    confused_pairs: list[ConfusedPair] = field(default_factory=list)
    line_results: list[GuessResult] = field(default_factory=list)
