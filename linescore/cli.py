"""CLI for linescore — thin consumer of the library."""

import subprocess
import argparse
import sys
from pathlib import Path

from linescore.scorer import score
from linescore.backends import Backend
from linescore.checks import Check
from linescore.reporting import format_text_report, format_json


_INSTALLABLE_BACKENDS = {
    "anthropic": ["anthropic>=0.39.0"],
    "llamacpp": ["llama-cpp-python>=0.3.0", "huggingface-hub>=0.20.0"],
}


def _handle_install(args: list[str]):
    if not args:
        print("Usage: linescore install <backend>")
        print(f"Available: {', '.join(_INSTALLABLE_BACKENDS)}")
        sys.exit(1)

    name = args[0]
    if name not in _INSTALLABLE_BACKENDS:
        print(f"Unknown backend: {name}")
        print(f"Available: {', '.join(_INSTALLABLE_BACKENDS)}")
        sys.exit(1)

    packages = _INSTALLABLE_BACKENDS[name]
    print(f"Installing {name} backend...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", *packages],
        capture_output=False,
        cwd="/",
    )
    if result.returncode != 0:
        sys.exit(result.returncode)

    # Download default model for llamacpp
    if name == "llamacpp":
        result = subprocess.run(
            [sys.executable, "-c", "from linescore.backends.llamacpp import download_default_model; download_default_model()"],
            cwd="/",
        )
        if result.returncode != 0:
            sys.exit(result.returncode)

    print(f"\n{name} backend installed. Use it with: linescore --backend {name}")


def _make_check(name: str) -> Check:
    if name == "line-to-function":
        from linescore.checks.line_to_function import LineToFunctionCheck
        return LineToFunctionCheck()
    elif name == "name-to-file":
        from linescore.checks.name_to_file import NameToFileCheck
        return NameToFileCheck()
    elif name == "file-to-folder":
        from linescore.checks.file_to_folder import FileToFolderCheck
        return FileToFolderCheck()
    else:
        print(f"Unknown check: {name}", file=sys.stderr)
        sys.exit(1)


def _make_backend(name: str, model: str | None) -> Backend:
    if name == "claude-code":
        from linescore.backends.claude_code import ClaudeCodeBackend
        return ClaudeCodeBackend(model=model) if model else ClaudeCodeBackend()
    elif name == "anthropic":
        from linescore.backends.anthropic import AnthropicBackend
        return AnthropicBackend(model=model) if model else AnthropicBackend()
    elif name == "llamacpp":
        from linescore.backends.llamacpp import LlamaCppBackend
        return LlamaCppBackend(model_path=model)
    else:
        print(f"Unknown backend: {name}", file=sys.stderr)
        sys.exit(1)


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
    # Handle `linescore install <backend>` before argparse
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        _handle_install(sys.argv[2:])
        return

    parser = argparse.ArgumentParser(
        prog="linescore",
        description="Score code quality via AI classification checks.\n\n"
                    "To install optional backends: linescore install <anthropic|llamacpp>",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Files or directories to analyze",
    )
    parser.add_argument(
        "--check",
        choices=["line-to-function", "name-to-file", "file-to-folder"],
        default="line-to-function",
        help="Which check to run (default: line-to-function)",
    )
    parser.add_argument(
        "--backend",
        choices=["claude-code", "anthropic", "llamacpp"],
        default="claude-code",
        help="LLM backend to use (default: claude-code)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name/path for the backend (default depends on backend)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output results as JSON",
    )
    parser.add_argument(
        "-n", "--max-items",
        type=int,
        default=None,
        help="Max items to sample per target (limits API calls)",
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
        help="Print each judgment as it completes",
    )
    args = parser.parse_args()

    check = _make_check(args.check)
    backend = _make_backend(args.backend, args.model)
    callback = _verbose_callback if args.verbose else None

    # For line-to-function, targets are source code strings (read from files).
    # For name-to-file and file-to-folder, targets are directory paths.
    if args.check == "line-to-function":
        files = _collect_python_files(args.paths)
        if not files:
            print("No Python files found.", file=sys.stderr)
            sys.exit(1)
        targets = [(str(f), f.read_text()) for f in files]
    else:
        # Directory-based checks: paths are directories
        targets = [(p, p) for p in args.paths]

    all_results = []

    for label, target in targets:
        print(f"Analyzing: {label}")

        try:
            result = score(
                check=check,
                backend=backend,
                target=target,
                max_items=args.max_items,
                workers=args.workers,
                on_result=callback,
            )
        except ValueError as e:
            print(f"  Skipping: {e}", file=sys.stderr)
            continue

        all_results.append((label, result))

        if not args.output_json:
            print(format_text_report(result, label))

    if args.output_json:
        import json
        from dataclasses import asdict
        output = [
            {**asdict(result), "file": label}
            for label, result in all_results
        ]
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
