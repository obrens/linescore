"""CLI for linescore — thin consumer of the library."""

import subprocess
import argparse
import sys
from pathlib import Path

from linescore.languages import Language
from linescore.models import ScoreResult
from linescore.scorer import score
from linescore.backends import Backend
from linescore.checks import Check
from linescore.reporting import format_text_report, format_text_summary, format_json


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


def _make_language(name: str) -> Language:
    if name == "python":
        from linescore.languages.python import PythonLanguage
        return PythonLanguage()
    else:
        print(f"Unknown language: {name}", file=sys.stderr)
        sys.exit(1)


def _make_check(name: str, language: Language) -> Check:
    if name == "line-to-function":
        from linescore.checks.line_to_function import LineToFunctionCheck
        return LineToFunctionCheck(language)
    elif name == "name-to-file":
        from linescore.checks.name_to_file import NameToFileCheck
        return NameToFileCheck(language)
    elif name == "file-to-folder":
        from linescore.checks.file_to_folder import FileToFolderCheck
        return FileToFolderCheck(language)
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


def _collect_source_files(paths: list[str], language: Language) -> list[Path]:
    """Resolve paths to a flat list of source files for the given language."""
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix in language.suffixes:
            files.append(path)
        elif path.is_dir():
            for suffix in language.suffixes:
                files.extend(sorted(path.rglob(f"*{suffix}")))
        else:
            print(f"Warning: skipping {p} (not a source file or directory)", file=sys.stderr)
    return files


def _find_dirs_with_sources(root: Path, language: Language) -> list[Path]:
    """Find all subdirectories under root that contain 2+ source files."""
    dirs: list[Path] = []
    for dirpath in sorted(root.rglob("*")):
        if not dirpath.is_dir():
            continue
        if any(part.startswith(".") or part in language.ignore_dirs
               for part in dirpath.relative_to(root).parts):
            continue
        source_count = sum(
            1 for f in dirpath.iterdir()
            if f.is_file() and f.suffix in language.suffixes
        )
        if source_count >= 2:
            dirs.append(dirpath)
    # Also check root itself
    root_source_count = sum(
        1 for f in root.iterdir()
        if f.is_file() and f.suffix in language.suffixes
    )
    if root_source_count >= 2:
        dirs.insert(0, root)
    return dirs


def _count_loc(path: Path, language: Language) -> int:
    """Count total lines of code in source files under a path."""
    if path.is_file():
        try:
            return len(path.read_text().splitlines())
        except (OSError, UnicodeDecodeError):
            return 0
    total = 0
    for suffix in language.suffixes:
        for f in path.rglob(f"*{suffix}"):
            if any(part.startswith(".") or part in language.ignore_dirs
                   for part in f.relative_to(path).parts):
                continue
            try:
                total += len(f.read_text().splitlines())
            except (OSError, UnicodeDecodeError):
                continue
    return total


def _dir_loc(directory: Path, language: Language) -> int:
    """Count LoC of source files directly in a directory (non-recursive)."""
    total = 0
    for f in directory.iterdir():
        if f.is_file() and f.suffix in language.suffixes:
            try:
                total += len(f.read_text().splitlines())
            except (OSError, UnicodeDecodeError):
                continue
    return total


def _plan_runs(
    paths: list[str],
    check_name: str,
    language: Language,
) -> list[tuple[str, str, str, int]]:
    """Plan which (check_name, label, target, loc) tuples to run.

    Returns a list of (check_name, label, target, loc) where target is either
    source code (for line-to-function) or a directory path (for others).
    loc is the lines of code for LoC-weighted scoring.
    """
    checks_to_run = (
        ["line-to-function", "name-to-file", "file-to-folder"]
        if check_name == "all"
        else [check_name]
    )

    runs: list[tuple[str, str, str, int]] = []

    for p in paths:
        path = Path(p)

        if path.is_file():
            if "line-to-function" in checks_to_run and path.suffix in language.suffixes:
                try:
                    source = path.read_text()
                    loc = len(source.splitlines())
                    runs.append(("line-to-function", str(path), source, loc))
                except (OSError, UnicodeDecodeError):
                    print(f"Warning: cannot read {p}", file=sys.stderr)
            continue

        if not path.is_dir():
            print(f"Warning: skipping {p} (not a source file or directory)", file=sys.stderr)
            continue

        # Directory: discover targets for each applicable check
        if "line-to-function" in checks_to_run:
            for src_file in _collect_source_files([str(path)], language):
                try:
                    source = src_file.read_text()
                    loc = len(source.splitlines())
                    runs.append(("line-to-function", str(src_file), source, loc))
                except (OSError, UnicodeDecodeError):
                    continue

        if "name-to-file" in checks_to_run:
            for d in _find_dirs_with_sources(path, language):
                loc = _dir_loc(d, language)
                runs.append(("name-to-file", str(d), str(d), loc))

        if "file-to-folder" in checks_to_run:
            loc = _count_loc(path, language)
            runs.append(("file-to-folder", str(path), str(path), loc))

    return runs


def _verbose_callback(result, completed, total):
    icon = "\u2713" if result.correct else "\u2717"
    print(
        f"  [{completed}/{total}] {icon}  "
        f"actual={result.actual}  "
        f"guess={result.guessed}  "
        f"conf={result.confidence:.2f}"
    )
    print(f"           {result.item[:80]}")


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
        choices=["all", "line-to-function", "name-to-file", "file-to-folder"],
        default="all",
        help="Which check to run (default: all)",
    )
    parser.add_argument(
        "--language",
        choices=["python"],
        default="python",
        help="Source language (default: python)",
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

    language = _make_language(args.language)
    backend = _make_backend(args.backend, args.model)
    callback = _verbose_callback if args.verbose else None

    runs = _plan_runs(args.paths, args.check, language)
    if not runs:
        print("No scorable targets found.", file=sys.stderr)
        sys.exit(1)

    # Cache check instances so we don't recreate them per run
    checks: dict[str, Check] = {}
    all_results: list[tuple[str, str, ScoreResult]] = []

    for check_name, label, target, loc in runs:
        if check_name not in checks:
            checks[check_name] = _make_check(check_name, language)

        print(f"[{check_name}] {label}")

        try:
            result = score(
                check=checks[check_name],
                backend=backend,
                target=target,
                max_items=args.max_items,
                workers=args.workers,
                on_result=callback,
            )
        except ValueError:
            # Single-category or empty: score as 0 (neutral)
            result = ScoreResult(
                score=0.0, total=0, correct=0,
                check=check_name, adjusted_score=0.0,
                chance_level=0.0, num_categories=0,
            )

        result.weight = loc
        all_results.append((check_name, label, result))

        if not args.output_json:
            print(format_text_report(result, label))

    if args.output_json:
        import json
        from dataclasses import asdict
        output = [
            {**asdict(result), "check": check_name, "target": label}
            for check_name, label, result in all_results
        ]
        print(json.dumps(output, indent=2))
    elif len(all_results) > 1:
        print(format_text_summary(all_results))


if __name__ == "__main__":
    main()
