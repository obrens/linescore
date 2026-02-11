"""
Code Quality Heuristic: Line Identifiability Score

Given a module, extracts all functions and their statements, then asks an AI
to guess which function each statement belongs to (given only the function names).
The accuracy of the AI's guesses is the "identifiability score" of the module.

Usage:
    python code_quality_heuristic.py <path_to_python_file> [--model MODEL] [--verbose]

Requires:
    pip install anthropic
    ANTHROPIC_API_KEY environment variable set
"""

import ast
import sys
import json
import random
import argparse
import textwrap
from pathlib import Path
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

import subprocess


# ---------------------------------------------------------------------------
# 1. Parsing: extract functions and their statements
# ---------------------------------------------------------------------------

@dataclass
class FunctionInfo:
    name: str
    args: list[str]
    statements: list[str] = field(default_factory=list)


class StatementExtractor(ast.NodeVisitor):
    """Walk a function body and collect individual statements as source lines."""

    SKIP_TYPES = (
        ast.FunctionDef, ast.AsyncFunctionDef,  # nested function defs
        ast.ClassDef,                            # nested classes
        ast.Import, ast.ImportFrom,              # imports inside functions
        ast.Pass, ast.Break, ast.Continue,       # trivial single-keyword stmts
    )

    def __init__(self, source_lines: list[str]):
        self.source_lines = source_lines
        self.statements: list[str] = []

    def _get_source(self, node: ast.AST) -> str | None:
        """Extract source text for a node, handling multi-line nodes."""
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        raw = self.source_lines[start:end]
        text = "\n".join(raw).strip()
        return text if text else None

    def _is_trivial(self, text: str) -> bool:
        """Filter out lines that are pure noise."""
        stripped = text.strip()
        # bare return, bare else/elif, just 'pass', single closing bracket, etc.
        if stripped in ("return", "return None", "else:", "finally:", ""):
            return True
        # just a variable name on its own, or ellipsis
        if stripped in ("...",):
            return True
        # self.x = x style (simple constructor assignment)
        if stripped.startswith("self.") and stripped.count("=") == 1:
            lhs, rhs = stripped.split("=", 1)
            attr = lhs.strip().removeprefix("self.").strip()
            if attr == rhs.strip():
                return True
        return False

    def visit_stmt(self, node: ast.AST):
        if isinstance(node, self.SKIP_TYPES):
            return
        # For compound statements (if/for/while/try/with), collect the whole
        # header line but also recurse into the body
        if isinstance(node, (ast.If, ast.For, ast.While, ast.AsyncFor,
                             ast.With, ast.AsyncWith, ast.Try,
                             ast.ExceptHandler)):
            # grab just the first line (the header)
            header = self.source_lines[node.lineno - 1].strip()
            if header and not self._is_trivial(header):
                self.statements.append(header)
            # recurse into child statements
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.AST) and hasattr(child, 'lineno'):
                    self.visit_stmt(child)
            return

        # Leaf statements: assignments, expressions, returns with values, raises
        src = self._get_source(node)
        if src and not self._is_trivial(src):
            self.statements.append(src)

    def extract_from_body(self, body: list[ast.stmt]) -> list[str]:
        for node in body:
            self.visit_stmt(node)
        return self.statements


def extract_functions(source: str) -> list[FunctionInfo]:
    """Parse a Python source file and extract top-level and class-level functions."""
    tree = ast.parse(source)
    source_lines = source.splitlines()
    functions: list[FunctionInfo] = []

    def process_func(node: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str = ""):
        name = f"{prefix}{node.name}" if prefix else node.name
        args = [arg.arg for arg in node.args.args if arg.arg != "self"]
        extractor = StatementExtractor(source_lines)
        stmts = extractor.extract_from_body(node.body)
        if stmts:  # skip empty functions
            functions.append(FunctionInfo(name=name, args=args, statements=stmts))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # determine if it's inside a class
            prefix = ""
            for cls in ast.walk(tree):
                if isinstance(cls, ast.ClassDef):
                    if node in ast.walk(cls):
                        prefix = f"{cls.name}."
                        break
            process_func(node, prefix)

    return functions


# ---------------------------------------------------------------------------
# 2. AI judging
# ---------------------------------------------------------------------------

def judge_statement(
    function_names: list[str],
    statement: str,
) -> tuple[str, float]:
    """Ask Claude Code to guess which function a statement belongs to.
    Returns (guessed_name, confidence)."""
    names_list = "\n".join(f"  - {n}" for n in function_names)
    prompt = (
        f"You are a code analysis tool. You will be given:\n"
        f"1. A list of function names from a Python module.\n"
        f"2. A single line/statement of code pulled from one of those functions.\n\n"
        f"Your task: guess which function the line most likely belongs to.\n\n"
        f"Respond with ONLY a JSON object: "
        f'{{"guess": "<function_name>", "confidence": <0.0-1.0>}}\n'
        f"No other text.\n\n"
        f"Function names in this module:\n{names_list}\n\n"
        f"Statement:\n```python\n{statement}\n```\n\n"
        f"Which function does this statement belong to?"
    )
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"  Claude Code error: {result.stderr[:200]}")
        return "", 0.0
    try:
        outer = json.loads(result.stdout)
        text = outer.get("result", "").strip()
    except json.JSONDecodeError:
        text = result.stdout.strip()
    # strip markdown fences if present
    text = text.removeprefix("```json").removesuffix("```").strip()
    try:
        data = json.loads(text)
        return data.get("guess", ""), data.get("confidence", 0.0)
    except json.JSONDecodeError:
        return text, 0.0


# ---------------------------------------------------------------------------
# 3. Scoring
# ---------------------------------------------------------------------------

@dataclass
class LineResult:
    statement: str
    actual_function: str
    guessed_function: str
    confidence: float
    correct: bool


def compute_score(
    source: str,
    model: str = "claude-sonnet-4-20250514",
    verbose: bool = False,
    max_statements: int | None = None,
    workers: int = 10,
) -> tuple[float, list[LineResult]]:
    """Run the heuristic on a Python source string.
    Returns (score 0.0-1.0, list of per-line results)."""
    functions = extract_functions(source)

    if len(functions) < 2:
        print("Need at least 2 functions with non-trivial statements to score.")
        return -1.0, []

    function_names = [f.name for f in functions]

    # build (statement, actual_function) pairs
    all_pairs = []
    for func in functions:
        for stmt in func.statements:
            all_pairs.append((stmt, func.name))

    # optionally sample if there are too many
    if max_statements and len(all_pairs) > max_statements:
        all_pairs = random.sample(all_pairs, max_statements)

    random.shuffle(all_pairs)

    results: list[LineResult] = [None] * len(all_pairs)
    completed = 0

    def judge_one(index: int, stmt: str, actual: str) -> tuple[int, LineResult]:
        guess, confidence = judge_statement(function_names, stmt)
        correct = guess == actual
        return index, LineResult(
            statement=stmt,
            actual_function=actual,
            guessed_function=guess,
            confidence=confidence,
            correct=correct,
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(judge_one, i, stmt, actual): i
            for i, (stmt, actual) in enumerate(all_pairs)
        }
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result
            completed += 1
            if verbose:
                r = result
                icon = "✓" if r.correct else "✗"
                print(f"  [{completed}/{len(all_pairs)}] {icon}  actual={r.actual_function}  "
                      f"guess={r.guessed_function}  conf={r.confidence:.2f}")
                print(f"           {r.statement[:80]}")

    score = sum(r.correct for r in results) / len(results) if results else 0.0
    return score, results


# ---------------------------------------------------------------------------
# 4. Reporting
# ---------------------------------------------------------------------------

def print_report(score: float, results: list[LineResult], functions: list[FunctionInfo]):
    total = len(results)
    correct = sum(r.correct for r in results)

    print("\n" + "=" * 60)
    print(f"  LINE IDENTIFIABILITY SCORE: {score:.1%}  ({correct}/{total})")
    print("=" * 60)

    # per-function breakdown
    print("\nPer-function breakdown:")
    func_names = sorted(set(r.actual_function for r in results))
    for fn in func_names:
        fn_results = [r for r in results if r.actual_function == fn]
        fn_correct = sum(r.correct for r in fn_results)
        fn_score = fn_correct / len(fn_results) if fn_results else 0
        bar = "█" * int(fn_score * 20) + "░" * (20 - int(fn_score * 20))
        print(f"  {fn:40s} {bar} {fn_score:.0%} ({fn_correct}/{len(fn_results)})")

    # worst misses: lines that were guessed wrong with high confidence
    wrong = [r for r in results if not r.correct]
    wrong.sort(key=lambda r: r.confidence, reverse=True)
    if wrong:
        print(f"\nMost confidently wrong guesses (potential decomposition issues):")
        for r in wrong[:5]:
            print(f"  • \"{r.statement[:70]}...\"" if len(r.statement) > 70
                  else f"  • \"{r.statement}\"")
            print(f"    actual: {r.actual_function}  →  guessed: {r.guessed_function} "
                  f"(confidence: {r.confidence:.0%})")

    # confusion pairs: which functions get confused with each other most
    confusion: dict[tuple[str, str], int] = {}
    for r in wrong:
        pair = (r.actual_function, r.guessed_function)
        confusion[pair] = confusion.get(pair, 0) + 1
    if confusion:
        print(f"\nMost confused function pairs:")
        for (a, b), count in sorted(confusion.items(), key=lambda x: -x[1])[:5]:
            print(f"  {a}  ↔  {b}  ({count} mismatches)")


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compute the Line Identifiability Score for a Python module."
    )
    parser.add_argument("file", help="Path to a Python source file")
    parser.add_argument("--model", default="claude-sonnet-4-20250514",
                        help="Anthropic model to use as judge")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print each line judgment")
    parser.add_argument("--max-statements", "-n", type=int, default=None,
                        help="Max statements to sample (to limit API calls)")
    parser.add_argument("--workers", "-w", type=int, default=10,
                        help="Number of parallel workers (default: 10)")
    args = parser.parse_args()

    source = Path(args.file).read_text()
    functions = extract_functions(source)

    print(f"Analyzing: {args.file}")
    print(f"Found {len(functions)} functions with non-trivial statements:")
    for f in functions:
        print(f"  • {f.name}({', '.join(f.args)}) — {len(f.statements)} statements")
    print(f"Total statements to judge: "
          f"{sum(len(f.statements) for f in functions)}")
    if args.max_statements:
        print(f"Sampling up to {args.max_statements} statements")
    print()

    score, results = compute_score(
        source,
        model=args.model,
        verbose=args.verbose,
        max_statements=args.max_statements,
        workers=args.workers,
    )

    if score >= 0:
        print_report(score, results, functions)


if __name__ == "__main__":
    main()