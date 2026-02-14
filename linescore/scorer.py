import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from linescore.backends import Backend, parse_judgment_json
from linescore.checks import Check
from linescore.models import (
    CategoryScore,
    ClassificationTask,
    ConfusedPair,
    GuessResult,
    ScoreResult,
)


def score(
    check: Check,
    backend: Backend,
    target: str,
    max_items: int | None = None,
    workers: int = 10,
    on_result: Callable[[GuessResult, int, int], None] | None = None,
) -> ScoreResult:
    """Score a target using a check and backend.

    Args:
        check: Defines what to classify (lines, names, files).
        backend: How to call the LLM.
        target: What to score (source code string, directory path, etc.).
        max_items: If set, randomly sample this many items.
        workers: Number of parallel backend calls.
        on_result: Optional callback invoked after each judgment with
                   (guess_result, completed_count, total_count).

    Returns:
        ScoreResult with scores and detailed results.

    Raises:
        ValueError: If fewer than 2 categories are found.
    """
    tasks = check.extract(target)

    if not tasks:
        raise ValueError("No classification tasks extracted from target.")

    candidates_set = set()
    for t in tasks:
        candidates_set.update(t.candidates)
    if len(candidates_set) < 2:
        raise ValueError(
            f"Need at least 2 categories to score, found {len(candidates_set)}."
        )

    # Optionally sample
    if max_items and len(tasks) > max_items:
        tasks = random.sample(tasks, max_items)

    random.shuffle(tasks)
    total = len(tasks)

    # Dispatch in parallel
    results: list[GuessResult] = [None] * total  # type: ignore[list-item]
    completed = 0

    def _score_one(index: int, task: ClassificationTask) -> tuple[int, GuessResult]:
        prompt = check.build_prompt(task.candidates, task.item)
        raw = backend.complete(prompt)
        jr = parse_judgment_json(raw)
        return index, GuessResult(
            item=task.item,
            actual=task.actual,
            guessed=jr.guess,
            confidence=jr.confidence,
            correct=jr.guess == task.actual,
            num_candidates=len(task.candidates),
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_score_one, i, task): i
            for i, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            idx, guess_result = future.result()
            results[idx] = guess_result
            completed += 1
            if on_result:
                on_result(guess_result, completed, total)

    return _build_result(results, tasks, check=check.name)


def _build_result(
    guess_results: list[GuessResult],
    tasks: list[ClassificationTask],
    check: str = "",
) -> ScoreResult:
    """Aggregate guess results into a ScoreResult."""
    total = len(guess_results)
    correct = sum(r.correct for r in guess_results)
    overall_score = correct / total if total > 0 else 0.0

    # Collect all unique categories from tasks
    all_categories: list[str] = []
    seen = set()
    for t in tasks:
        if t.actual not in seen:
            all_categories.append(t.actual)
            seen.add(t.actual)

    # Per-category scores
    cat_results: dict[str, list[GuessResult]] = {}
    for r in guess_results:
        cat_results.setdefault(r.actual, []).append(r)

    category_scores = []
    for cat_name in all_categories:
        results = cat_results.get(cat_name, [])
        fc = sum(r.correct for r in results)
        ft = len(results)
        category_scores.append(CategoryScore(
            name=cat_name,
            total=ft,
            correct=fc,
            score=fc / ft if ft > 0 else 0.0,
            results=results,
        ))

    # Per-task chance-adjusted scores
    adjusted_scores = []
    chance_levels = []
    for r in guess_results:
        k = r.num_candidates if r.num_candidates >= 2 else len(all_categories)
        chance = 1.0 / k
        score_i = 1.0 if r.correct else 0.0
        adj_i = (score_i - chance) / (1.0 - chance)
        adjusted_scores.append(adj_i)
        chance_levels.append(chance)

    adjusted_score = sum(adjusted_scores) / len(adjusted_scores) if adjusted_scores else 0.0
    chance_level = sum(chance_levels) / len(chance_levels) if chance_levels else 0.0

    # Collect all unique candidates across tasks
    all_candidates = set()
    for t in tasks:
        all_candidates.update(t.candidates)

    # Confused pairs
    confusion: dict[tuple[str, str], int] = {}
    for r in guess_results:
        if not r.correct and r.guessed:
            pair = (r.actual, r.guessed)
            confusion[pair] = confusion.get(pair, 0) + 1

    confused_pairs = [
        ConfusedPair(category_a=a, category_b=b, count=c)
        for (a, b), c in sorted(confusion.items(), key=lambda x: -x[1])
    ]

    return ScoreResult(
        score=overall_score,
        total=total,
        correct=correct,
        check=check,
        adjusted_score=adjusted_score,
        chance_level=chance_level,
        num_categories=len(all_candidates),
        category_scores=category_scores,
        confused_pairs=confused_pairs,
        results=guess_results,
    )
