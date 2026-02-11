# Design Decisions

## Naming
- **Package name is `linescore`**. Considered `linefit`, `identiscore`, `funcsort`, `codeprint`, `funcid`. User prefers `linescore` — it's punchy and matches the repo/GitHub name. Renaming the repo would be more hassle than it's worth at this stage. Can always rename before there are real users.

## Architecture

### Library-first design
- The scoring engine is the product. CLI/CI/IDE extensions are consumers.
- Public API: `from linescore import score, Backend, Check, Language` + dataclasses.

### Backends + Checks + Languages
- **Backends** = how to call an LLM. Protocol: `complete(prompt: str) -> str`.
  - `ClaudeCodeBackend`: subprocess to `claude` CLI.
  - `AnthropicBackend`: Anthropic Python SDK (messages API).
  - `LlamaCppBackend`: llama-cpp-python bindings (local, in-process, thread-safe via lock).
- **Checks** = what to score. Protocol: `extract(target) -> list[ClassificationTask]` + `build_prompt(candidates, item) -> str`. Checks are language-agnostic.
  - `LineToFunctionCheck`: can the LLM guess which function a line belongs to?
  - `NameToFileCheck`: can the LLM guess which file a function/class name belongs to?
  - `FileToFolderCheck`: can the LLM guess which folder a file/subfolder belongs to?
- **Languages** = all language-specific behavior. Protocol: `extract_functions()`, `extract_names()`, `suffixes`, `ignore_dirs`, `ignore_suffixes`.
  - `PythonLanguage`: `.py` files, `__pycache__`/`.pyc` filtering, AST-based extraction.
- Each check takes a `Language` in its constructor. Adding a new language requires zero changes to checks.

### No backward compatibility
- We don't care about backward compat unless explicitly told to.

### Parsers are internal
- `parsers/` is an internal package used by `PythonLanguage`. Not part of the public API.

### `cli.py` lives inside `linescore/` package
- It's convenient and idiomatic to have it in the package directory.
- What matters is dependency flow: CLI depends on the library, not the other way around.
- CLI is NOT exported as part of the library's public API (`__init__.py` does not re-export it).
- Entry point: `linescore = "linescore.cli:main"` in pyproject.toml.
- Also runnable via `python -m linescore` (via `__main__.py`).
- `linescore install <backend>` installs optional dependencies + downloads models.

### Reporting lives in the library
- `linescore/reporting.py` provides `format_text_report()` and `format_json()` as convenience formatters.
- Report labels adapt based on `ScoreResult.check` field (e.g. "Per-function" vs "Per-file" vs "Per-folder").
- Consumers can still format `ScoreResult` however they want — the formatters are optional.

### Pluggable protocols
- `Backend` protocol: `complete(prompt: str) -> str`
- `Check` protocol: `extract(target) -> list[ClassificationTask]` + `build_prompt(candidates, item) -> str`
- `Language` protocol: `extract_functions()`, `extract_names()`, `suffixes`, `ignore_dirs`, `ignore_suffixes`
- `parse_judgment_json()` is shared by all backends — it lives in `backends/__init__.py` and the scorer calls it after getting raw text from the backend.

### Parallelism
- The library owns parallelism (thread pool in `score()`).
- Default: 10 workers.
- `LlamaCppBackend` serializes calls internally (llama-cpp-python is not thread-safe).
- Cross-target parallelism is the caller's responsibility.

## Models

### Generic field names
- `GuessResult` fields: `item`, `actual`, `guessed` (not check-specific).
- `ConfusedPair` fields: `category_a`, `category_b`.
- `ScoreResult` fields: `category_scores`, `results`.
- `ScoreResult.check` field identifies the check type for reporting.

### ClassificationTask
- Generic task: `item` (what to classify), `actual` (correct answer), `candidates` (all options).
- Each check's `extract()` method produces these. The scorer + backend process them generically.

## Scoring approach
- Names-only in the prompt for line-to-function (not full signatures). Language plugin decides what to expose.
- No thresholds in the library — that's policy, belongs to consumers.
- Statement filtering is conservative for now — being too aggressive hides real signals.

## Infrastructure
- `pyproject.toml` build backend: `setuptools.build_meta`.
- Installed editable in venv at `~/priv_projects/venvs/linescore/`.
- Global availability via symlink: `~/.local/bin/linescore` -> venv bin.
- Zero runtime dependencies for core — just stdlib + `claude` CLI on PATH.
- `anthropic` and `llama-cpp-python` are optional dependencies, installed via `linescore install <backend>`.
- Install subprocess runs from `cwd="/"` to avoid CWD import poisoning.
- LlamaCpp default model: Qwen2.5-Coder-1.5B-Instruct (Q4_K_M), auto-downloaded to `~/.linescore/models/`.
- Unit tests required. Tests use mock backends (no API cost).
