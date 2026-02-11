import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from linescore.models import (
    ConfusedPair,
    FunctionInfo,
    FunctionScore,
    JudgmentResult,
    LineResult,
    ModuleResult,
)
from linescore.parsers import Parser
from linescore.judges import Judge


def score_module(
    source: str,
    parser: Parser,
    judge: Judge,
    max_statements: int | None = None,
    workers: int = 10,
    on_result: Callable[[LineResult, int, int], None] | None = None,
) -> ModuleResult:
    """Score a module's code quality by line identifiability.

    Args:
        source: The source code to analyze.
        parser: Extracts functions and statements from the source.
        judge: AI that guesses which function a statement belongs to.
        max_statements: If set, randomly sample this many statements.
        workers: Number of parallel judge calls.
        on_result: Optional callback invoked after each judgment with
                   (line_result, completed_count, total_count).

    Returns:
        ModuleResult with scores and detailed results.

    Raises:
        ValueError: If fewer than 2 functions with statements are found.
    """
    functions = parser.extract_functions(source)

    if len(functions) < 2:
        raise ValueError(
            f"Need at least 2 functions with non-trivial statements to score, "
            f"found {len(functions)}."
        )

    function_names = [f.name for f in functions]

    # Build (statement, actual_function) pairs
    all_pairs = []
    for func in functions:
        for stmt in func.statements:
            all_pairs.append((stmt, func.name))

    # Optionally sample
    if max_statements and len(all_pairs) > max_statements:
        all_pairs = random.sample(all_pairs, max_statements)

    random.shuffle(all_pairs)
    total = len(all_pairs)

    # Dispatch judgments in parallel
    results: list[LineResult] = [None] * total  # type: ignore[list-item]
    completed = 0

    def _judge_one(index: int, stmt: str, actual: str) -> tuple[int, LineResult]:
        jr = judge.judge(function_names, stmt)
        return index, LineResult(
            statement=stmt,
            actual_function=actual,
            guessed_function=jr.guess,
            confidence=jr.confidence,
            correct=jr.guess == actual,
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_judge_one, i, stmt, actual): i
            for i, (stmt, actual) in enumerate(all_pairs)
        }
        for future in as_completed(futures):
            idx, line_result = future.result()
            results[idx] = line_result
            completed += 1
            if on_result:
                on_result(line_result, completed, total)

    return _build_result(results, functions)


def _build_result(
    line_results: list[LineResult],
    functions: list[FunctionInfo],
) -> ModuleResult:
    """Aggregate line results into a ModuleResult."""
    total = len(line_results)
    correct = sum(r.correct for r in line_results)
    score = correct / total if total > 0 else 0.0

    # Per-function scores
    func_results: dict[str, list[LineResult]] = {}
    for r in line_results:
        func_results.setdefault(r.actual_function, []).append(r)

    function_scores = []
    for func in functions:
        results = func_results.get(func.name, [])
        fc = sum(r.correct for r in results)
        ft = len(results)
        function_scores.append(FunctionScore(
            name=func.name,
            total=ft,
            correct=fc,
            score=fc / ft if ft > 0 else 0.0,
            results=results,
        ))

    # Confused pairs
    confusion: dict[tuple[str, str], int] = {}
    for r in line_results:
        if not r.correct and r.guessed_function:
            pair = (r.actual_function, r.guessed_function)
            confusion[pair] = confusion.get(pair, 0) + 1

    confused_pairs = [
        ConfusedPair(function_a=a, function_b=b, count=c)
        for (a, b), c in sorted(confusion.items(), key=lambda x: -x[1])
    ]

    return ModuleResult(
        score=score,
        total=total,
        correct=correct,
        function_scores=function_scores,
        confused_pairs=confused_pairs,
        line_results=line_results,
    )
