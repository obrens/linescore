# Plan: Scoring improvements, summary output, multi-check defaults

## Context

Linescore v0.2 has three backends and three checks working. Four improvements are needed before the tool produces meaningful, comparable results:

1. **Scoring favors modules with fewer functions** — A file with 2 functions gets 50% from random guessing; one with 10 functions gets 10%. Raw accuracy is not comparable across targets.
2. **No summary at the end** — Multi-file runs print per-file reports but no aggregate view.
3. **Only one check runs at a time** — Users must manually specify `--check` three times to get the full picture.
4. **No reference scores** — Users have no baseline to know if 75% is good or bad.

## Step 1: Chance-adjusted scoring

**Problem**: Raw accuracy = `correct / total`. Random baseline = `1/k` where k = number of categories. A 75% score with 2 functions (baseline 50%) is less impressive than 75% with 10 functions (baseline 10%).

**Formula**: `adjusted = (raw - 1/k) / (1 - 1/k)`
- Normalizes to 0.0 = random guessing, 1.0 = perfect, negative = worse than random
- Well-known (Cohen's kappa simplification for uniform prior)

**Changes**:

`linescore/models.py`:
- `ScoreResult`: add `adjusted_score: float`, `chance_level: float`, `num_categories: int`

`linescore/scorer.py` — `_build_result()`:
- Compute `k = len(candidates_set)`, `chance = 1/k`, `adjusted = (raw - chance) / (1 - chance)`
- Pass to ScoreResult constructor

`linescore/reporting.py` — `format_text_report()`:
- Header line: show adjusted score as primary, raw in parentheses
  - `SCORE: 66.7% adjusted  (75.0% raw, 3/4, chance=50.0%)`

`linescore/reporting.py` — `format_json()`:
- `adjusted_score`, `chance_level`, `num_categories` included automatically via `asdict`

**Files**: `models.py`, `scorer.py`, `reporting.py`, `tests/test_scorer.py`, `tests/test_reporting.py`

## Step 2: Run all checks by default

**Problem**: Users must run `--check line-to-function`, then `--check name-to-file`, then `--check file-to-folder` separately.

**Design**: `--check` accepts `"all"` (new default), which runs every applicable check:
- **line-to-function**: runs once per source file (target = file contents)
- **name-to-file**: runs once per directory input (target = directory path)
- **file-to-folder**: runs once per directory input (target = directory path)

When a single file is passed, only line-to-function applies. When a directory is passed, all three apply (line-to-function runs per source file found in the directory).

**Changes**:

`linescore/cli.py`:
- `--check` choices: add `"all"`, make it the default
- New `_plan_runs()` function returns `list[tuple[str, Check, str, str]]` — `(check_name, check_instance, label, target)`:
  - For each file path: one `line-to-function` run
  - For each directory path: one `line-to-function` per source file + one `name-to-file` + one `file-to-folder`
  - When `--check` is specific (not `"all"`): filter to just that check
- Main loop iterates over `_plan_runs()` output instead of the current hardcoded if/else

**Files**: `cli.py`

## Step 3: Summary at end of multi-target runs

**Problem**: When scoring multiple files/directories, the user sees per-target reports scroll by with no aggregate view.

**Design**: After all runs complete, print a summary table + overall score.

**Changes**:

`linescore/reporting.py` — new `format_text_summary()`:
```
============================================================
  SUMMARY: 3 targets, 2 checks
============================================================
  Check              Target               Adjusted   Raw
  line-to-function   email.py             44.4%      66.7%
  line-to-function   api.py               88.9%      90.0%
  name-to-file       src/                 75.0%      87.5%
------------------------------------------------------------
  Overall (adjusted):  69.4%
============================================================
```
- Input: `list[tuple[str, str, ScoreResult]]` — `(check_name, label, result)`
- Overall adjusted score: mean of per-run adjusted scores (each run already normalized for its k)

`linescore/cli.py`:
- Collect all `(check_name, label, result)` triples during the main loop
- After the loop, if `len(all_results) > 1` and not `--json`, call `format_text_summary()`
- JSON mode: already outputs a list of all results (no change needed, `adjusted_score` will be in there from step 1)

**Files**: `reporting.py`, `cli.py`, `tests/test_reporting.py`

## Step 4: Reference scores / benchmarking (design only)

This is a larger effort. For now, just lay the groundwork:

`linescore/cli.py` — add `linescore benchmark` subcommand:
- Ships with a list of ~5 well-known open source Python repos (e.g., `requests`, `flask`, `black`, `httpx`, `fastapi`)
- Clones them to a temp dir, runs all checks, prints a comparison table
- Stores results in `~/.linescore/benchmarks/` as JSON for future comparison

This step is **design-only in this plan** — implement the subcommand skeleton and the repo list, but the actual benchmarking infrastructure (cloning, caching, comparison UI) is a follow-up. The main deliverable is steps 1-3.

## Implementation order

1. Chance-adjusted scoring (models + scorer + reporting + tests)
2. Multi-check `--check all` (CLI restructuring)
3. Summary output (reporting + CLI)
4. Benchmark skeleton (CLI only, optional/stretch)

## Verification

- All existing 64 tests pass after each step
- New tests for adjusted scoring: verify formula with known k values (k=2: 75% raw -> 50% adjusted; k=5: 40% raw -> 25% adjusted)
- `linescore --help` shows `all` as default for `--check`
- `linescore .` runs all three checks on the current directory
- `linescore somefile.py` runs only line-to-function
- Summary appears at the end of multi-target runs
- JSON output includes `adjusted_score`, `chance_level`, `num_categories`
