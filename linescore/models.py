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
class LineResult:
    """Result of judging a single statement."""
    statement: str
    actual_function: str
    guessed_function: str
    confidence: float
    correct: bool


@dataclass
class FunctionScore:
    """Score breakdown for a single function."""
    name: str
    total: int
    correct: int
    score: float
    results: list[LineResult] = field(default_factory=list)


@dataclass
class ConfusedPair:
    """Two functions whose lines get confused with each other."""
    function_a: str
    function_b: str
    count: int


@dataclass
class ModuleResult:
    """Complete scoring result for a module."""
    score: float
    total: int
    correct: int
    function_scores: list[FunctionScore] = field(default_factory=list)
    confused_pairs: list[ConfusedPair] = field(default_factory=list)
    line_results: list[LineResult] = field(default_factory=list)
