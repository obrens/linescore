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
  - `GroqBackend`: Groq SDK (cloud inference). Default model: `qwen/qwen3-32b`. Uses `reasoning_effort="none"` to disable Qwen3's thinking mode (saves tokens, avoids `<think>` blocks in responses).
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

### Chance-adjusted scoring
- Raw accuracy is not comparable across targets with different numbers of categories (a 75% score with 2 functions is less impressive than 75% with 10).
- Adjusted score: `(raw - 1/k) / (1 - 1/k)` where k = number of candidates. 0.0 = random guessing, 1.0 = perfect, negative = worse than random.
- Adjustment is computed **per-task** then averaged, not on the aggregate. This handles checks where different tasks have different candidate set sizes (e.g., file-to-folder with neighborhood scoping).

### LoC weighting in summaries
- When aggregating scores across multiple runs (e.g., across files in a repo), each run is weighted by its **lines of code**, not equally.
- Rationale: LoC is a consistent measure of "how much code does this unit represent" across all check types. A 500-line file should matter more than a 5-line file in the overall score.
- Task count (number of classification items) was considered as an alternative weight, but it means different things per check (statements vs names vs folder children) and doesn't consistently reflect code volume.

### Single-category items score 0
- Items with < 2 categories (single-function files, directories with 1 source file, etc.) cannot be meaningfully classified — there's nothing to compare against.
- Rather than excluding them (which inflates the score by only counting evaluable code), they receive an **adjusted score of 0** — the neutral "no evidence of quality" baseline.
- Combined with LoC weighting, this is self-correcting:
  - Small single-function files: tiny weight, barely affect the overall score. Correct — a small focused file is fine.
  - Large single-function files: significant weight, pulls score toward 0. Also correct — a 500-line un-decomposed file is a design smell.
- Excluding single-category items entirely would mean a repo that's 80% god-files only gets scored on the 20% that has multiple functions, which is misleading.

### File-to-folder neighborhood scoping
- File-to-folder candidates are restricted to the **local neighborhood**: the item's parent folder, sibling folders, and the grandparent folder.
- Rationale: a file only needs to be sortable within its local component. A file in `src/auth/` shouldn't need to be distinguishable from folders under `src/billing/utils/` — those are different components. The check measures local organizational quality, not global tree-wide sortability.
- For the root folder, the neighborhood is root + its direct child folders (since root has no siblings or parent).

## Infrastructure
- `pyproject.toml` build backend: `setuptools.build_meta`.
- Installed editable in venv at `~/priv_projects/venvs/linescore/`.
- Global availability via symlink: `~/.local/bin/linescore` -> venv bin.
- Zero runtime dependencies for core — just stdlib + `claude` CLI on PATH.
- `anthropic`, `llama-cpp-python`, and `groq` are optional dependencies, installed via `linescore install <backend>`.
- Install subprocess runs from `cwd="/"` to avoid CWD import poisoning.
- LlamaCpp default model: Qwen2.5-Coder-1.5B-Instruct (Q4_K_M), auto-downloaded to `~/.linescore/models/`.
- Unit tests required. Tests use mock backends (no API cost).

### Backend file naming
- Backend module files must NOT shadow the SDK package they import. E.g., the Groq backend lives in `groq_backend.py`, not `groq.py`, because `import groq` inside `groq.py` would resolve to itself instead of the installed SDK.

### Response parsing
- `parse_judgment_json()` in `backends/__init__.py` handles multiple response formats: direct JSON, Claude Code wrapped (`{"result": "..."}`), markdown-fenced JSON, and `<think>...</think>`-wrapped responses (from reasoning models like Qwen3).
- The `<think>` stripping is a safety net — backends should disable thinking at the API level when possible (e.g., `reasoning_effort="none"` for Groq) to avoid wasting tokens.

### Check scoping — each check is local
- **line-to-function**: scoped to a single file. Can you sort lines to functions *within a file*?
- **name-to-file**: scoped to a single folder (non-recursive). Can you sort names to files *within a folder*? Cross-folder sorting is not meaningful — different components can have similar concerns.
- **file-to-folder**: scoped to the local neighborhood (parent, siblings, grandparent). Can you sort files to folders *among neighbors*?
- This locality is intentional. Each check measures organizational quality at its level of the hierarchy, not global sortability.
