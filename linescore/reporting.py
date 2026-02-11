"""Convenience formatters for ModuleResult.

These are optional — consumers can format results however they want.
"""

import json
from dataclasses import asdict

from linescore.models import ModuleResult


def format_text_report(result: ModuleResult, file_path: str = "") -> str:
    """Format a ModuleResult as a human-readable text report."""
    lines: list[str] = []

    header = "LINE IDENTIFIABILITY SCORE"
    if file_path:
        header = f"{file_path} — {header}"

    lines.append("")
    lines.append("=" * 60)
    lines.append(f"  {header}: {result.score:.1%}  ({result.correct}/{result.total})")
    lines.append("=" * 60)

    # Per-function breakdown
    if result.function_scores:
        lines.append("")
        lines.append("Per-function breakdown:")
        scored = [fs for fs in result.function_scores if fs.total > 0]
        for fs in sorted(scored, key=lambda f: f.score):
            bar = "\u2588" * int(fs.score * 20) + "\u2591" * (20 - int(fs.score * 20))
            lines.append(
                f"  {fs.name:40s} {bar} {fs.score:.0%} ({fs.correct}/{fs.total})"
            )

    # Most confidently wrong guesses
    wrong = [r for r in result.line_results if not r.correct]
    wrong.sort(key=lambda r: r.confidence, reverse=True)
    if wrong:
        lines.append("")
        lines.append("Most confidently wrong guesses (potential decomposition issues):")
        for r in wrong[:5]:
            stmt_display = f'"{r.statement[:70]}..."' if len(r.statement) > 70 else f'"{r.statement}"'
            lines.append(f"  * {stmt_display}")
            lines.append(
                f"    actual: {r.actual_function}  ->  guessed: {r.guessed_function} "
                f"(confidence: {r.confidence:.0%})"
            )

    # Confused pairs
    if result.confused_pairs:
        lines.append("")
        lines.append("Most confused function pairs:")
        for cp in result.confused_pairs[:5]:
            lines.append(
                f"  {cp.function_a}  <->  {cp.function_b}  ({cp.count} mismatches)"
            )

    return "\n".join(lines)


def format_json(result: ModuleResult, file_path: str = "") -> str:
    """Format a ModuleResult as JSON."""
    data = asdict(result)
    if file_path:
        data["file"] = file_path
    return json.dumps(data, indent=2)
