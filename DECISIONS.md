# Design Decisions

## Naming
- **Package name is `linescore`**. Considered `linefit`, `identiscore`, `funcsort`, `codeprint`, `funcid`. User prefers `linescore` — it's punchy and matches the repo/GitHub name. Renaming the repo would be more hassle than it's worth at this stage. Can always rename before there are real users.

## Architecture

### Library-first design
- The scoring engine is the product. CLI, CI plugins, IDE extensions are consumers.
- Public API: `from linescore import score_module, PythonParser, ClaudeCodeJudge`

### `cli.py` lives inside `linescore/` package
- It's convenient and idiomatic to have it in the package directory.
- What matters is dependency flow: CLI depends on the library, not the other way around.
- CLI is NOT exported as part of the library's public API (`__init__.py` does not re-export it).
- Entry point: `linescore = "linescore.cli:main"` in pyproject.toml.
- Also runnable via `python -m linescore` (via `__main__.py`).

### Reporting lives in the library
- Initially planned as consumer-only concern, but user pointed out that forcing every consumer to write their own reporting is too much friction.
- `linescore/reporting.py` provides `format_text_report()` and `format_json()` as convenience formatters.
- Consumers can still format `ModuleResult` however they want — the formatters are optional.

### Pluggable parsers and judges via Protocol
- `Parser` protocol: `extract_functions(source: str) -> list[FunctionInfo]`
- `Judge` protocol: `judge(function_names: list[str], statement: str) -> JudgmentResult`
- What goes into the prompt (names only vs signatures) is the parser's decision, not the scorer's. If someone wants signatures, they implement their own parser.

### Parallelism
- The library owns parallelism (thread pool in `score_module()`).
- Default: 10 workers.
- Cross-file parallelism is the caller's responsibility.

## Scoring approach
- Names-only in the prompt (not full signatures). User's explicit preference for Python. Parser decides what to expose.
- No `--model` flag — not needed for Claude Code judge. Use cheapest possible model.
- No thresholds in the library — that's policy, belongs to consumers.
- Statement filtering is conservative for now — being too aggressive hides real signals (a function full of generic code IS informative).

## Infrastructure
- `pyproject.toml` build backend: `setuptools.build_meta` (not the legacy backend — that one doesn't work).
- Installed editable in venv at `~/priv_projects/venvs/linescore/`.
- Global availability via symlink: `~/.local/bin/linescore` -> venv bin.
- Zero runtime dependencies — just stdlib + `claude` CLI on PATH.
- Unit tests required as part of MVP. Tests use mock judges (no API cost).