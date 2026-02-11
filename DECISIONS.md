# Design Decisions

## Naming
- **Package name is `linescore`**. Considered `linefit`, `identiscore`, `funcsort`, `codeprint`, `funcid`. User prefers `linescore` — it's punchy and matches the repo/GitHub name. Renaming the repo would be more hassle than it's worth at this stage. Can always rename before there are real users.

## Architecture

### Library-first design
- The scoring engine is the product. CLI/CI/IDE extensions are consumers.
- Public API: `from linescore import score, Backend, Check` + dataclasses.

### Backends + Checks separation
- **Backends** = how to call an LLM. Protocol: `complete(prompt: str) -> str`.
  - `ClaudeCodeBackend`: subprocess to `claude` CLI.
  - `AnthropicBackend`: Anthropic Python SDK (messages API).
  - `LlamaCppBackend`: llama-cpp-python bindings (local, in-process).
- **Checks** = what to score. Protocol: `extract(target) -> list[ClassificationTask]` + `build_prompt(candidates, item) -> str`.
  - `LineToFunctionCheck`: can the LLM guess which function a line belongs to?
  - `NameToFileCheck`: can the LLM guess which file a function/class name belongs to?
  - `FileToFolderCheck`: can the LLM guess which folder a file/subfolder belongs to?
- This separation means adding a new LLM provider or a new scoring check requires no changes to existing code.

### No backward compatibility
- We don't care about backward compat unless explicitly told to. The old `judges/` package and `score_module()` function were removed in favor of the cleaner `backends/` + `checks/` + `score()` architecture.

### Parsers are internal
- `parsers/` is an internal package used by `LineToFunctionCheck`. Not part of the public API. The `Parser` protocol was removed from exports.

### `cli.py` lives inside `linescore/` package
- It's convenient and idiomatic to have it in the package directory.
- What matters is dependency flow: CLI depends on the library, not the other way around.
- CLI is NOT exported as part of the library's public API (`__init__.py` does not re-export it).
- Entry point: `linescore = "linescore.cli:main"` in pyproject.toml.
- Also runnable via `python -m linescore` (via `__main__.py`).

### Reporting lives in the library
- `linescore/reporting.py` provides `format_text_report()` and `format_json()` as convenience formatters.
- Consumers can still format `ScoreResult` however they want — the formatters are optional.

### Pluggable backends and checks via Protocol
- `Backend` protocol: `complete(prompt: str) -> str`
- `Check` protocol: `extract(target) -> list[ClassificationTask]` + `build_prompt(candidates, item) -> str`
- `parse_judgment_json()` is shared by all backends — it lives in `backends/__init__.py` and the scorer calls it after getting raw text from the backend.

### Parallelism
- The library owns parallelism (thread pool in `score()`).
- Default: 10 workers.
- Cross-target parallelism is the caller's responsibility.

## Models

### Renamed for generality
- `LineResult` → `GuessResult`: works for any check, not just lines.
- `FunctionScore` → `CategoryScore`: categories = functions, files, or folders.
- `ModuleResult` → `ScoreResult`: not always scoring a "module".
- `ScoreResult.check` field identifies the check type for reporting.

### ClassificationTask
- Generic task: `item` (what to classify), `actual` (correct answer), `candidates` (all options).
- Each check's `extract()` method produces these. The scorer + backend process them generically.

## Scoring approach
- Names-only in the prompt for line-to-function (not full signatures). Parser decides what to expose.
- No thresholds in the library — that's policy, belongs to consumers.
- Statement filtering is conservative for now — being too aggressive hides real signals.

## Infrastructure
- `pyproject.toml` build backend: `setuptools.build_meta`.
- Installed editable in venv at `~/priv_projects/venvs/linescore/`.
- Global availability via symlink: `~/.local/bin/linescore` -> venv bin.
- Zero runtime dependencies for core — just stdlib + `claude` CLI on PATH.
- `anthropic` and `llama-cpp-python` are optional dependencies.
- Unit tests required. Tests use mock backends (no API cost).
