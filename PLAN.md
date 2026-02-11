# Plan: New backends + new scoring checks

## Context

Linescore currently has one backend (Claude Code subprocess) and one scoring check (line→function). The user wants:
- **Three backend plugins**: Claude Code (existing), Anthropic API (direct SDK), llama-cpp-python (local, free)
- **Three scoring checks**: line→function (existing), function/class name→file (new), file/folder→parent folder (new)

The current architecture mixes "how to call an LLM" and "what to ask it" inside `ClaudeCodeJudge`. We need to separate these concerns.

## Architecture

**Backends** = how to call an LLM. Protocol: `complete(prompt: str) -> str`. Returns raw text.
- `backends/claude_code.py` — subprocess to `claude` CLI (extracted from existing judge)
- `backends/anthropic.py` — `anthropic` Python SDK
- `backends/llamacpp.py` — `llama_cpp` Python bindings (in-process, no server)

**Checks** = what to score. Protocol: `extract(target) -> list[ClassificationTask]` + `build_prompt(candidates, item) -> str`.
- `checks/line_to_function.py` — given a source file, can the LLM guess which function a code line belongs to?
- `checks/name_to_file.py` — given a directory of files, can the LLM guess which file a function/class name belongs to?
- `checks/file_to_folder.py` — given a directory tree, can the LLM guess which folder a file/subfolder belongs to?

**Scorer** = orchestration. Takes a check + backend + target, dispatches in parallel, aggregates results.


## Models

Rename existing models to be generic (this is v0.1 with no external users, so no compat concern):

| Current | New | Why |
|---------|-----|-----|
| `LineResult` | `GuessResult` | Works for any check, not just lines |
| `FunctionScore` | `CategoryScore` | Categories = functions, files, or folders |
| `ModuleResult` | `ScoreResult` | Not always scoring a "module" |
| `ConfusedPair` | stays `ConfusedPair` | Already generic enough |
| `FunctionInfo` | stays `FunctionInfo` | Parser-specific, not used by new checks |
| `JudgmentResult` | stays `JudgmentResult` | Already generic (guess + confidence) |

Add:
```python
@dataclass
class ClassificationTask:
    item: str           # thing to classify (a statement, a name, a filename)
    actual: str         # correct category
    candidates: list[str]  # all possible categories
```

`ScoreResult` gets a `check: str` field ("line-to-function", "name-to-file", "file-to-folder") so reporting knows what labels to use.

## File structure after implementation

```
linescore/
    __init__.py              # update exports
    __main__.py              # unchanged
    models.py                # rename LineResult→GuessResult etc, add ClassificationTask
    scorer.py                # add generic score(), keep score_module() as wrapper
    reporting.py             # adapt to generic model names
    cli.py                   # add --check, --backend, --model flags
    parsers/
        __init__.py          # unchanged
        python.py            # unchanged
    judges/
        __init__.py          # unchanged (backward compat)
        claude_code.py       # unchanged (backward compat)
    backends/
        __init__.py          # Backend protocol + shared parse_judgment_json()
        claude_code.py       # extracted subprocess logic
        anthropic.py         # anthropic SDK
        llamacpp.py          # llama-cpp-python
    checks/
        __init__.py          # Check protocol + ClassificationTask
        line_to_function.py  # uses PythonParser, existing prompt
        name_to_file.py      # AST extraction of names across files
        file_to_folder.py    # directory tree walking
tests/
    test_backends.py         # test response parsing, mock subprocess/API/llama
    test_check_line_to_function.py   # extraction + prompt building
    test_check_name_to_file.py       # extraction from temp directory
    test_check_file_to_folder.py     # extraction from temp directory
    test_scorer.py           # update for renamed models, add generic score() tests
    test_parser_python.py    # update imports for renamed models
    test_reporting.py        # update for renamed models
    test_judge_claude_code.py # keep as-is (backward compat)
```

## Implementation steps

### 1. Rename models + update all references
- `models.py`: `LineResult`→`GuessResult`, `FunctionScore`→`CategoryScore`, `ModuleResult`→`ScoreResult`
- Update `scorer.py`, `reporting.py`, `cli.py`, `__init__.py`, all tests
- All 34 tests must still pass after rename

### 2. Add `backends/` package
- `backends/__init__.py`: `Backend` protocol + `parse_judgment_json()` (extracted from `ClaudeCodeJudge._parse_response`)
- `backends/claude_code.py`: subprocess to `claude` CLI, calls `parse_judgment_json`
- `backends/anthropic.py`: uses `anthropic` SDK (Anthropic client, messages.create)
- `backends/llamacpp.py`: uses `llama_cpp.Llama` for in-process inference
- Tests: mock subprocess/SDK/Llama, verify prompt passthrough and response parsing

### 3. Add `checks/` package
- `checks/__init__.py`: `Check` protocol, `ClassificationTask` dataclass
- `checks/line_to_function.py`: takes source string, uses `PythonParser`, builds line→function prompt
- `checks/name_to_file.py`: takes directory path, walks .py files, extracts function/class names via AST, builds name→file prompt
- `checks/file_to_folder.py`: takes directory path, walks tree, builds file→folder prompt
- Tests: verify extraction produces correct tasks from known inputs

### 4. Add generic `score()` function to `scorer.py`
```python
def score(
    check: Check,
    backend: Backend,
    target: str | Path,
    max_items: int | None = None,
    workers: int = 10,
    on_result: Callable | None = None,
) -> ScoreResult:
```
- Keep existing `score_module()` as backward-compat wrapper
- Tests: use FakeBackend with each check type

### 5. Update reporting for generic models
- `format_text_report()` and `format_json()` work with renamed `ScoreResult`
- Section headers adapt based on `result.check` field

### 6. Update CLI
- Add `--check` flag: `line-to-function` (default), `name-to-file`, `file-to-folder`
- Add `--backend` flag: `claude-code` (default), `anthropic`, `llamacpp`
- Add `--model` flag: model name for the chosen backend
- Wire up: instantiate check + backend based on flags, call `score()`

### 7. Update pyproject.toml
```toml
[project.optional-dependencies]
anthropic = ["anthropic>=0.39.0"]
llamacpp = ["llama-cpp-python>=0.3.0"]
all = ["anthropic>=0.39.0", "llama-cpp-python>=0.3.0"]
```

### 8. Update DECISIONS.md
Record all new design decisions.

## Verification
- All existing tests pass after model rename (step 1)
- New backend tests pass with mocks (step 2)
- New check tests pass with temp directories (step 3)
- Generic scorer tests pass with fake backend (step 4)
- `linescore --help` shows new flags (step 6)
- Smoke test: `linescore --check name-to-file --backend llamacpp --model <local-model> src/` runs end-to-end
