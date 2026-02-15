# Project Status — linescore v0.2.0

## What we have

A code quality scorer with three checks, four backends, chance-adjusted scoring, and LoC-weighted summaries. Scores Python code by testing whether an AI can identify where code elements belong in the project structure.

**Architecture:** Library (`linescore/`) with pluggable backends, checks, and languages, consumed by a thin CLI. Installed via `pip install -e .`, invoked as `linescore <path>`.

**Checks:**
- `LineToFunctionCheck` — can the LLM guess which function a code statement belongs to?
- `NameToFileCheck` — can the LLM guess which file a function/class name belongs to?
- `FileToFolderCheck` — can the LLM guess which folder a file/subfolder belongs to? (neighborhood-scoped)

**Backends:**
- `ClaudeCodeBackend` — subprocess to `claude` CLI (default, zero deps)
- `AnthropicBackend` — Anthropic Python SDK (`linescore install anthropic`)
- `LlamaCppBackend` — local llama-cpp-python (`linescore install llamacpp`)
- `GroqBackend` — Groq cloud API with Qwen3-32B (`linescore install groq`)

**Scoring:**
- Chance-adjusted scores: `(raw - 1/k) / (1 - 1/k)`, computed per-task to handle variable candidate set sizes
- LoC-weighted summaries: overall score weighted by lines of code, not equal per-run
- Single-category items (< 2 functions/files) score 0 instead of being excluded
- Flat summary table shown after multi-run sessions

**Tests:** 94 unit tests, all passing. Tests use mock backends (no API cost).

## What works well

- The heuristic surfaces real signals about code organization quality.
- `linescore .` runs all three checks on the current directory with recursive target discovery.
- Adjusted scoring makes results comparable across targets with different numbers of categories.
- LoC weighting ensures the overall score reflects the whole codebase proportionally.
- Response parser handles multiple LLM output formats (direct JSON, Claude Code wrapped, markdown-fenced, thinking-wrapped).

## Known issues and limitations

- **No API key setup guidance.** `linescore install anthropic` and `linescore install groq` install the SDK but don't help with API key configuration. Users get confusing errors from deep in the SDK when keys are missing.
- **No caching.** Running the same file twice pays full API cost again.
- **No hierarchical folder report.** The flat summary shows per-run scores but doesn't group by folder for drill-down. (Planned as Step 3b.)
- **Python only.** No other language parsers yet.
- **No benchmarks.** No reference scores from well-known repos to compare against. (Planned as Step 5.)

## What changed since v0.1.0

- Added `AnthropicBackend`, `LlamaCppBackend`, `GroqBackend`
- Added `NameToFileCheck` and `FileToFolderCheck` (was line-to-function only)
- Added `Language` protocol; unified language-specific behavior in `PythonLanguage`
- Rewrote scorer with per-task chance-adjusted scoring
- Added `--check all` (new default) with recursive directory walking
- File-to-folder narrowed to local neighborhood (parent, siblings, grandparent)
- Added LoC-weighted flat summary
- Single-category items score 0 instead of being skipped
- Groq backend: disabled Qwen3 thinking mode (`reasoning_effort="none"`)
- Parser: handles `<think>...</think>` blocks from reasoning models
- Tests: 34 → 94
