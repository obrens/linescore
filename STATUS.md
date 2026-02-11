# Project Status — linescore v0.1.0

## What we have

A working MVP that scores Python code quality by "line identifiability" — how accurately an AI can guess which function a code statement belongs to, given only function names.

**Architecture:** Library (`linescore/`) with pluggable parsers and judges, consumed by a thin CLI (`cli.py`). Installed via `pip install -e .`, invoked as `linescore <path>`.

**Components:**
- `PythonParser` — AST-based extraction of functions and their statements, with filtering of trivial lines.
- `ClaudeCodeJudge` — shells out to `claude` CLI, defaults to Haiku model.
- `score_module()` — core scorer with parallel dispatch, progress callbacks.
- `reporting.py` — convenience formatters (text table, JSON).
- 34 unit tests, all passing. Tests use mock judges so they run instantly with no API cost.

## What works well

- The heuristic surfaces real signals. In the smoke test, it correctly identified that `judge_statement` and `process_func` get confused — they do similar subprocess/JSON work at the same abstraction level.
- The per-function breakdown and confused-pairs output are immediately actionable.
- The parser/judge protocol separation is clean. Adding a new language or AI backend means implementing one method.
- Zero runtime dependencies. Just stdlib + `claude` on PATH.

## Known issues and limitations

**Haiku might be too weak for this task.** The smoke test scored 20% on 5 statements, which is low even accounting for sample noise. Haiku may not have enough reasoning ability to reliably match statements to function names. Worth testing with Sonnet to see if the score difference is significant — if it is, the default model choice needs revisiting. The tradeoff is cost: a full run on a 150-statement file is 150 API calls.

**Statement filtering needs iteration.** The current filter removes obvious noise (pass, bare return, self.x = x) but lets through generic statements like `except json.JSONDecodeError:` that are inherently ambiguous. Being too aggressive with filtering risks hiding real problems (a function full of generic code *is* a signal), but some lines will always be unguessable. The right balance will emerge from running it on real codebases and looking at which wrong guesses are informative vs noise.

**Subprocess overhead is significant.** Each judgment spawns a `claude` process. For 150 statements at 10 workers, that's ~15 sequential batches of process spawns. A direct Anthropic API judge would be meaningfully faster and allow control over temperature, max tokens, etc.

**No caching.** Running the same file twice pays full API cost again. For local dev use this is annoying; for CI it would be wasteful.

**Single-file scoring only.** The tool scores one module at a time. Cross-module analysis (e.g. "these two files have overlapping responsibilities") is out of scope, but aggregating per-file scores across a project is a natural next step for the CLI.

## Potential next steps

### High priority (making it actually useful day-to-day)

1. **Test with Sonnet vs Haiku** — Run the same file with both models and compare scores. If Haiku is too noisy, either default to Sonnet or make the model easily configurable.

2. **Direct API judge** — Implement `AnthropicApiJudge` using the `anthropic` Python SDK. Eliminates subprocess overhead, gives control over model/temperature/tokens, and enables batching. This would be noticeably faster and cheaper.

3. **Result caching** — Cache judgments keyed on (statement, function_names_hash, model). Skip re-judging unchanged statements. This makes re-runs on slightly modified files near-instant.

4. **Prompt tuning** — The current prompt is basic. Experiment with: telling the AI the language explicitly, giving it permission to say "ambiguous" instead of guessing randomly, adjusting confidence calibration. Small prompt changes could significantly affect score quality.

### Medium priority (making it practical for teams)

5. **Multi-file summary** — When run on a directory, print an aggregate summary (worst files, average score, total stats) after individual reports.

6. **Config file** — A `.linescore.toml` or similar that sets defaults (model, workers, max-statements, exclude patterns) per project. Avoids typing flags every time.

7. **Threshold / exit code** — `--threshold 0.5` that returns exit code 1 if any file scores below. Enables CI gating.

8. **Git diff mode** — Only score files changed since a given ref. `linescore --diff main` to score only what's in your PR.

### Lower priority (extending the concept)

9. **Other language parsers** — TypeScript/JavaScript would be the highest-value next language. Java/Kotlin after that.

10. **Other judge backends** — OpenAI, local models (for teams that can't use Anthropic), etc.

11. **Confidence-weighted scoring** — Instead of raw accuracy, weight by the AI's confidence. A high-confidence wrong guess is worse than a low-confidence one. This could be a more nuanced metric.

12. **Historical tracking** — Store scores over time to show trends. "This module's score dropped from 72% to 58% in the last month."

## Naming

The package is called `linescore`.
