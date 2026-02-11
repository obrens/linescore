# Linescore MVP Plan

## 1. Understanding the Project

**The idea:** Given a line of code from a module, and the names of all functions in that module, can an AI guess which function the line came from? The accuracy of its guesses is a proxy for code quality — specifically for how well functions are decomposed, named, and cohesive.

This is clever because it tests multiple quality dimensions at once:
- **Cohesion** — a focused function's lines will "sound like" that function.
- **Naming quality** — if names are vague, the AI can't match lines to them.
- **Abstraction boundaries** — if two functions work at the same level doing similar things, their lines become interchangeable.
- **Decomposition quality** — both over-decomposition (thin wrappers at the same abstraction level) and under-decomposition (god functions) lower the score.

It's symmetric: it penalizes both too-big and too-thin functions. Most code quality heuristics only push in one direction.

## 2. Critical Assessment of the POC

### What works well
- The AST-based statement extraction is the right approach (vs. raw text lines).
- Filtering trivial lines (pass, bare return, self.x = x) is necessary and the POC does a reasonable job.
- The per-function breakdown and "confused pairs" in the report are genuinely useful — they make the output actionable, not just a number.
- Parallel execution was the right call for usability.

### Issues and concerns

**Bug in `extract_functions`:** The parent-class detection logic is O(n²) and incorrect for edge cases. It does `ast.walk(tree)` inside `ast.walk(tree)`, and the `node in ast.walk(cls)` check will match functions in nested classes incorrectly. Should be replaced with a proper parent-tracking visitor.

**Statement filtering is incomplete.** Lines that should probably be filtered but aren't:
- Logging calls (`logger.info(...)`, `print(...)`) — these are everywhere and uninformative.
- Generic exception raising (`raise ValueError(...)`) without distinctive messages.
- Type annotations and docstrings that survived filtering.
- Lines like `elif condition:` where `condition` is generic.

Counter-point: being too aggressive with filtering defeats the purpose. If a function is full of generic logging calls, that *is* a signal about the code. The right balance needs experimentation. For MVP, I'd keep filtering conservative and iterate.

**The prompt is basic.** The AI is told to guess with only function names and one statement. It might benefit from:
- Being told the language.
- Getting function signatures (arguments) — the conversation discussed this but went with names-only for Python. I think names-only is the right default, with signatures as an option.
- A system prompt that calibrates its behavior (e.g., "If genuinely ambiguous, say so rather than guessing randomly").

However, prompt simplicity is a feature for reproducibility. I'd leave it mostly as-is for MVP and note it as an area for experimentation.

**Claude Code subprocess is slow.** Each judgment spawns a full process. With 100 statements and 10 workers, that's 10 concurrent subprocess spawns. It works, but:
- Startup overhead dominates for a task where the AI's thinking time should be milliseconds.
- There's no way to control model selection, temperature, or token limits.
- Rate limiting is implicit (whatever Claude Code does internally).

For MVP this is acceptable since the user explicitly wants Claude Code as the only backend. But the architecture should make it trivial to swap in a direct API client later.

**No caching.** Running the tool twice on the same unchanged file costs the same. Not critical for MVP but worth noting.

**The model parameter is unused.** The `--model` flag in the CLI doesn't actually affect anything since Claude Code chooses its own model. Should be removed or replaced with a `--judge` flag.

## 3. Architectural Decisions

### 3.1 Library-first design

The conversation's conclusion is right: the scoring engine is the product; how you invoke it is a consumer concern. The library should expose a clean API that a CLI, CI plugin, IDE extension, or web service can call.

```
linescore/               # the library
    __init__.py          # public API
    models.py            # FunctionInfo, LineResult, ModuleResult
    scorer.py            # core scoring loop
    parsers/
        __init__.py      # Parser protocol
        python.py        # Python AST parser
    judges/
        __init__.py      # Judge protocol
        claude_code.py   # Claude Code subprocess

cli.py                   # thin CLI consumer (outside the library)
```

### 3.2 Key interfaces

**Parser protocol:**
```python
class Parser(Protocol):
    def extract_functions(self, source: str) -> list[FunctionInfo]: ...
```

**Judge protocol:**
```python
class Judge(Protocol):
    def judge(self, function_names: list[str], statement: str) -> JudgmentResult: ...
```

Where `JudgmentResult` has `guess: str` and `confidence: float`.

**Scorer — the core:**
```python
def score_module(
    source: str,
    parser: Parser,
    judge: Judge,
    max_statements: int | None = None,
    workers: int = 10,
) -> ModuleResult: ...
```

This is the main library entry point. It:
1. Uses the parser to extract functions.
2. Builds (statement, actual_function) pairs.
3. Shuffles and optionally samples them.
4. Dispatches judgments in parallel.
5. Returns a `ModuleResult` with all the data.

### 3.3 Parallelism

The library should own parallelism. The scoring loop is the hot path, and thread pool management is tightly coupled to how judgments are dispatched. The caller just passes `workers=N`.

Cross-file parallelism (scoring multiple files in parallel) is the caller's responsibility — the CLI can use multiprocessing or sequential iteration as it sees fit.

### 3.4 Reporting

Reporting is explicitly NOT in the library. The library returns `ModuleResult` — a structured data object. What you do with it (print a table, write JSON, post a GitHub comment, render HTML) is the consumer's business.

For the MVP CLI, I'll include two output modes:
- Human-readable table (default) — the same style as the POC.
- JSON (`--json` flag) — for piping to other tools.

### 3.5 Collecting / file discovery

For MVP, the CLI just takes file paths or directories. No git-diff integration, no special discovery logic. Just:
```
linescore my_module.py
linescore src/
linescore file1.py file2.py file3.py
```

When given a directory, it recursively finds Python files.

### 3.6 Thresholds

The library returns numbers. It does not enforce thresholds. That's policy, and policy belongs to the consumer. The MVP CLI won't have a `--threshold` flag. If someone wants CI enforcement later, they write a wrapper or we add it to the CLI then.

### 3.7 Naming

The repo is called `linescore`. The conversation discussed `identiscore` vs `linescore`. I'll use `linescore` as the package name to match the repo, but this is easily changed.

## 4. MVP Plan — Step by Step

### Step 1: Set up project structure
- Create the `linescore/` package directory structure.
- Add a `pyproject.toml` with basic metadata (name, version, dependencies, entry point).
- Only dependency: none for the library itself. The CLI needs nothing beyond stdlib.
- Create the entry point so `python -m linescore` and potentially a `linescore` console script work.

### Step 2: Define models (`linescore/models.py`)
Move and refine the dataclasses from the POC:
- `FunctionInfo` — name, args, statements.
- `JudgmentResult` — guess, confidence.
- `LineResult` — statement, actual_function, guessed_function, confidence, correct.
- `FunctionScore` — name, total, correct, score, results.
- `ModuleResult` — overall score, total/correct counts, function_scores, confused_pairs, line_results.

`ModuleResult` should contain everything a reporter needs, pre-computed.

### Step 3: Define Parser protocol + Python parser (`linescore/parsers/`)
- Define `Parser` as a `Protocol` with one method: `extract_functions(source: str) -> list[FunctionInfo]`.
- Move the Python AST parsing code from POC to `linescore/parsers/python.py`.
- Fix the parent-class detection bug.
- Keep statement filtering as-is for now (conservative). Add a TODO for experimentation.

### Step 4: Define Judge protocol + Claude Code judge (`linescore/judges/`)
- Define `Judge` as a `Protocol` with one method: `judge(function_names: list[str], statement: str) -> JudgmentResult`.
- Move the Claude Code subprocess logic from POC to `linescore/judges/claude_code.py`.
- Clean up the prompt slightly (specify that it's Python code, tighten the instruction).
- Remove the unused `--model` parameter.

### Step 5: Implement scorer (`linescore/scorer.py`)
- The core `score_module()` function.
- Takes `source`, `parser`, `judge`, `max_statements`, `workers`.
- Returns `ModuleResult`.
- Handles shuffling, sampling, parallel dispatch, and result aggregation.
- Computes per-function scores, confused pairs, everything the POC's report used.

### Step 6: Public API (`linescore/__init__.py`)
- Re-export `score_module`, all models, the parser and judge protocols.
- This is the "front door" of the library. A consumer should be able to:
  ```python
  from linescore import score_module, PythonParser, ClaudeCodeJudge
  result = score_module(source, PythonParser(), ClaudeCodeJudge(), workers=10)
  ```

### Step 7: CLI (`cli.py`)
A thin script that:
- Accepts file paths and directories.
- Recursively finds `.py` files in directories.
- Instantiates `PythonParser` and `ClaudeCodeJudge`.
- Calls `score_module()` for each file.
- Prints human-readable output or JSON.
- Flags: `--json`, `--max-statements/-n`, `--workers/-w`, `--verbose/-v`.
- Wired as a `[project.scripts]` entry point in `pyproject.toml`.

### Step 8: Smoke test
- Run it on the POC file itself.
- Run it on a few real Python files to sanity-check results.
- Verify JSON output parses correctly.

## 5. What's explicitly OUT of MVP scope
- CI integration (thresholds, GitHub comments, exit codes).
- Languages other than Python.
- AI backends other than Claude Code.
- Caching of results.
- Configuration files (per-project settings).
- Any form of UI beyond the terminal.
- Publishing to PyPI.

These are all natural next steps but not MVP.

## 6. Open Questions for You

1. **Name:** The repo is `linescore`, the conversation settled on `identiscore`. Which do you want for the package name?

2. **Function signatures in the prompt:** For Python, the conversation agreed on names-only. Should the MVP also support passing full signatures as an option (e.g., `--with-signatures`), or is names-only sufficient?

3. **What to do with the unused `--model` flag:** Remove it entirely, or repurpose it as a passthrough to `claude -p --model X`?

4. **Parallelism default:** The POC uses 10 workers. Is that a good default for your setup, or do you hit rate limits?

5. **Test suite:** Do you want unit tests as part of the MVP, or is "runs correctly on real files" sufficient for now?

### My answers

1. I prefer linescore to identiscore. But do try to come up with something as punchy and linescore, but a bit more specific about what it does.
2. No, I prefer names only. This should, however, be something that the parser decides. So if somebody doesn't like it, they can implement their own parser.
3. No need for it. However, is it possible to actually choose the model that Claude Code is using? If so, then using the cheapest possible model should be good for the MVP, as we don't want to waste money on a simple test like this.
4. Let's go with 10, and we'll see how it goes.
5. Yes, it needs unit tests.


## Additional comments by the user

1. I'm not sure about the reporting. Sure, it makes sense to treat it as separate from the library, but also it seems like a lot of work for the consumer to have to write their own reporting.
