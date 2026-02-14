"""Convenience formatters for ScoreResult.

These are optional — consumers can format results however they want.
"""

import json
from dataclasses import asdict

from linescore.models import ScoreResult

_CHECK_LABELS = {
    "line-to-function": {
        "header": "LINE IDENTIFIABILITY SCORE",
        "breakdown": "Per-function breakdown:",
        "wrong": "Most confidently wrong guesses (potential decomposition issues):",
        "confused": "Most confused function pairs:",
    },
    "name-to-file": {
        "header": "NAME-TO-FILE SCORE",
        "breakdown": "Per-file breakdown:",
        "wrong": "Most confidently wrong guesses:",
        "confused": "Most confused file pairs:",
    },
    "file-to-folder": {
        "header": "FILE-TO-FOLDER SCORE",
        "breakdown": "Per-folder breakdown:",
        "wrong": "Most confidently wrong guesses:",
        "confused": "Most confused folder pairs:",
    },
}

_DEFAULT_LABELS = {
    "header": "CLASSIFICATION SCORE",
    "breakdown": "Per-category breakdown:",
    "wrong": "Most confidently wrong guesses:",
    "confused": "Most confused category pairs:",
}


def format_text_report(result: ScoreResult, file_path: str = "") -> str:
    """Format a ScoreResult as a human-readable text report."""
    labels = _CHECK_LABELS.get(result.check, _DEFAULT_LABELS)
    lines: list[str] = []

    header = labels["header"]
    if file_path:
        header = f"{file_path} — {header}"

    lines.append("")
    lines.append("=" * 60)
    lines.append(
        f"  {header}: {result.adjusted_score:.1%} adjusted"
        f"  ({result.score:.1%} raw, {result.correct}/{result.total},"
        f" chance={result.chance_level:.1%})"
    )
    lines.append("=" * 60)

    # Per-category breakdown
    if result.category_scores:
        lines.append("")
        lines.append(labels["breakdown"])
        scored = [cs for cs in result.category_scores if cs.total > 0]
        for cs in sorted(scored, key=lambda c: c.score):
            bar = "\u2588" * int(cs.score * 20) + "\u2591" * (20 - int(cs.score * 20))
            lines.append(
                f"  {cs.name:40s} {bar} {cs.score:.0%} ({cs.correct}/{cs.total})"
            )

    # Most confidently wrong guesses
    wrong = [r for r in result.results if not r.correct]
    wrong.sort(key=lambda r: r.confidence, reverse=True)
    if wrong:
        lines.append("")
        lines.append(labels["wrong"])
        for r in wrong[:5]:
            display = f'"{r.item[:70]}..."' if len(r.item) > 70 else f'"{r.item}"'
            lines.append(f"  * {display}")
            lines.append(
                f"    actual: {r.actual}  ->  guessed: {r.guessed} "
                f"(confidence: {r.confidence:.0%})"
            )

    # Confused pairs
    if result.confused_pairs:
        lines.append("")
        lines.append(labels["confused"])
        for cp in result.confused_pairs[:5]:
            lines.append(
                f"  {cp.category_a}  <->  {cp.category_b}  ({cp.count} mismatches)"
            )

    return "\n".join(lines)


def format_text_summary(
    results: list[tuple[str, str, ScoreResult]],
) -> str:
    """Format a summary table for multiple scoring runs.

    Overall score is LoC-weighted: each run contributes proportionally
    to its lines of code. Runs with weight=0 fall back to equal weighting.

    Args:
        results: List of (check_name, label, ScoreResult) triples.
    """
    total_loc = sum(r.weight for _, _, r in results)

    lines: list[str] = []
    lines.append("")
    lines.append("=" * 70)
    loc_note = f", {total_loc} LoC" if total_loc > 0 else ""
    lines.append(f"  SUMMARY: {len(results)} runs{loc_note}")
    lines.append("=" * 70)

    # Column widths
    check_w = max(len(r[0]) for r in results)
    label_w = max(len(r[1]) for r in results)
    check_w = max(check_w, 5)  # minimum
    label_w = min(max(label_w, 6), 40)  # cap at 40

    header = (
        f"  {'Check':<{check_w}}  {'Target':<{label_w}}"
        f"  {'Adjusted':>8}  {'Raw':>8}  {'LoC':>5}"
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    for check_name, label, result in results:
        display_label = label if len(label) <= label_w else "..." + label[-(label_w - 3):]
        lines.append(
            f"  {check_name:<{check_w}}  {display_label:<{label_w}}"
            f"  {result.adjusted_score:>7.1%}  {result.score:>7.1%}"
            f"  {result.weight:>5}"
        )

    # Overall — LoC-weighted if weights are available, else equal
    if results:
        if total_loc > 0:
            weighted = sum(r.adjusted_score * r.weight for _, _, r in results)
            overall = weighted / total_loc
        else:
            overall = sum(r.adjusted_score for _, _, r in results) / len(results)
        lines.append("  " + "-" * (len(header) - 2))
        lines.append(f"  Overall (LoC-weighted adjusted): {overall:.1%}")

    lines.append("=" * 70)
    return "\n".join(lines)


def format_json(result: ScoreResult, file_path: str = "") -> str:
    """Format a ScoreResult as JSON."""
    data = asdict(result)
    if file_path:
        data["file"] = file_path
    return json.dumps(data, indent=2)
