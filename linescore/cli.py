"""CLI for linescore — thin consumer of the library."""

import argparse
import sys
from pathlib import Path

from linescore import score_module, ModuleResult
from linescore.parsers.python import PythonParser
from linescore.judges.claude_code import ClaudeCodeJudge
from linescore.reporting import format_text_report, format_json


def _collect_python_files(paths: list[str]) -> list[Path]:
    """Resolve paths to a flat list of .py files."""
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
        else:
            print(f"Warning: skipping {p} (not a .py file or directory)", file=sys.stderr)
    return files


def _verbose_callback(result, completed, total):
    icon = "\u2713" if result.correct else "\u2717"
    print(
        f"  [{completed}/{total}] {icon}  "
        f"actual={result.actual_function}  "
        f"guess={result.guessed_function}  "
        f"conf={result.confidence:.2f}"
    )
    print(f"           {result.statement[:80]}")


def main():
    parser = argparse.ArgumentParser(
        prog="linescore",
        description="Score code quality by line identifiability.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Python files or directories to analyze",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output results as JSON",
    )
    parser.add_argument(
        "-n", "--max-statements",
        type=int,
        default=None,
        help="Max statements to sample per file (limits API calls)",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=10,
        help="Number of parallel workers (default: 10)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print each line judgment as it completes",
    )
    args = parser.parse_args()

    files = _collect_python_files(args.paths)
    if not files:
        print("No Python files found.", file=sys.stderr)
        sys.exit(1)

    py_parser = PythonParser()
    judge = ClaudeCodeJudge()
    callback = _verbose_callback if args.verbose else None

    all_results: list[tuple[str, ModuleResult]] = []

    for file_path in files:
        source = file_path.read_text()
        print(f"Analyzing: {file_path}")

        try:
            result = score_module(
                source=source,
                parser=py_parser,
                judge=judge,
                max_statements=args.max_statements,
                workers=args.workers,
                on_result=callback,
            )
        except ValueError as e:
            print(f"  Skipping: {e}", file=sys.stderr)
            continue

        all_results.append((str(file_path), result))

        if not args.output_json:
            print(format_text_report(result, str(file_path)))

    if args.output_json:
        import json
        output = []
        for file_path, result in all_results:
            from dataclasses import asdict
            data = asdict(result)
            data["file"] = file_path
            output.append(data)
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
