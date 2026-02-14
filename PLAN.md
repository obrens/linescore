# Plan: Scoring improvements, summary output, multi-check defaults

## Context

Linescore v0.2 has three backends and three checks working. Five improvements are needed before the tool produces meaningful, comparable results:

1. **Scoring favors modules with fewer functions** — A file with 2 functions gets 50% from random guessing; one with 10 functions gets 10%. Raw accuracy is not comparable across targets.
2. **Only one check runs at a time** — Users must manually specify `--check` three times to get the full picture. Running on a directory doesn't recurse into subdirectories for name-to-file.
3. **No summary or hierarchical view** — Multi-file runs print per-file reports but no aggregate view. No way to see per-folder quality breakdown across checks.
4. **file-to-folder candidates are too broad** — Every folder in the entire tree is a candidate for every task, even folders in completely unrelated components.
5. **No reference scores** — Users have no baseline to know if 75% is good or bad.

## Step 1: Chance-adjusted scoring

**Problem**: Raw accuracy = `correct / total`. Random baseline = `1/k` where k = number of categories. A 75% score with 2 functions (baseline 50%) is less impressive than 75% with 10 functions (baseline 10%).

**Formula**: `adjusted = (raw - 1/k) / (1 - 1/k)`
- Normalizes to 0.0 = random guessing, 1.0 = perfect, negative = worse than random
- Well-known (Cohen's kappa simplification for uniform prior)

**Per-task vs per-result adjustment**: For line-to-function and name-to-file, all tasks within a single `score()` call share the same candidate set, so `k` is uniform and the adjustment can be computed once on the aggregate result. However, after Step 4 (file-to-folder neighborhood scoping), different tasks may have different candidate sets (different k). The adjustment should therefore be computed **per-task** and then averaged: `adjusted = mean(per_task_adjusted_i)` where each `adjusted_i = (correct_i - 1/k_i) / (1 - 1/k_i)`. For uniform-k checks, this reduces to the same formula. This keeps the scorer general from the start.

**Changes**:

`linescore/models.py`:
- `ScoreResult`: add `adjusted_score: float`, `chance_level: float`, `num_categories: int`
- `GuessResult`: add `num_candidates: int` (the k for this specific task)

`linescore/scorer.py` — `_score_one()`:
- Record `len(task.candidates)` into `GuessResult.num_candidates`

`linescore/scorer.py` — `_build_result()`:
- Per-task adjusted: for each guess, compute `k_i = guess.num_candidates`, `adj_i = (1 - 1/k_i) / (1 - 1/k_i)` if correct, else `(0 - 1/k_i) / (1 - 1/k_i)`
- `adjusted_score = mean(adj_i)`
- `chance_level = mean(1/k_i)` (weighted average chance)
- `num_categories = len(union of all candidates)` (for display purposes)

`linescore/reporting.py` — `format_text_report()`:
- Header line: show adjusted score as primary, raw in parentheses
  - `SCORE: 66.7% adjusted  (75.0% raw, 3/4, chance=50.0%)`

`linescore/reporting.py` — `format_json()`:
- `adjusted_score`, `chance_level`, `num_categories` included automatically via `asdict`

**Files**: `models.py`, `scorer.py`, `reporting.py`, `tests/test_scorer.py`, `tests/test_reporting.py`

## Step 2: Run all checks by default, with recursive directory walking

**Problem**: Users must run `--check line-to-function`, then `--check name-to-file`, then `--check file-to-folder` separately. Also, when passing a directory, name-to-file only scores immediate files — it doesn't recurse into subdirectories. To score a whole repo, you'd need to manually invoke it per subdirectory.

**Design**: `--check` accepts `"all"` (new default), which runs every applicable check. When a directory is passed, the CLI walks it recursively to discover all scorable targets:

- **line-to-function**: runs once per source file found anywhere in the tree
- **name-to-file**: runs once per subdirectory that has 2+ source files (the check itself already handles single-directory scope — the CLI just needs to discover and iterate the directories)
- **file-to-folder**: runs once with the root directory as target (it already walks the tree internally)

When a single file is passed, only line-to-function applies.

**Architectural note**: The check classes and `scorer.score()` don't change — each `score()` call still takes one check + one target and returns one `ScoreResult`. The new work is in the CLI's target discovery. This is important because it means the hierarchical reporting in Step 3 is also just orchestration + aggregation over the same flat `score()` results.

**Changes**:

`linescore/cli.py`:
- `--check` choices: add `"all"`, make it the default
- New `_plan_runs()` function returns `list[tuple[str, Check, str, str]]` — `(check_name, check_instance, label, target)`:
  - For each file path: one `line-to-function` run
  - For each directory path:
    - One `line-to-function` per source file found recursively
    - One `name-to-file` per subdirectory with 2+ source files
    - One `file-to-folder` for the root directory
  - When `--check` is specific (not `"all"`): filter to just that check
- Main loop iterates over `_plan_runs()` output instead of the current hardcoded if/else

**Files**: `cli.py`

## Step 3: Summary and hierarchical report

**Problem**: When scoring multiple files/directories, the user sees per-target reports scroll by with no aggregate view. For whole-repo runs, there's no way to see which folders score well or poorly across checks.

**Design**: Two levels of summary after all runs complete:

### 3a: Flat summary with LoC weighting (always shown when multiple runs)

```
============================================================
  SUMMARY: 3 runs, 1847 LoC scored
============================================================
  Check              Target               Adjusted   Raw     LoC
  line-to-function   email.py             44.4%      66.7%   120
  line-to-function   api.py               88.9%      90.0%   340
  name-to-file       src/                 75.0%      87.5%   460
------------------------------------------------------------
  Overall (LoC-weighted adjusted):  72.1%
============================================================
```

Each run is weighted by its LoC in the overall score: `weighted_mean = sum(adj_i * loc_i) / sum(loc_i)`. This means a 500-line file matters more than a 5-line file — the overall score reflects "how much of your code is well-organized."

### Single-category items score 0

Items with < 2 categories (single-function files, directories with 1 source file) receive adjusted_score=0 instead of being excluded. Combined with LoC weighting, this is self-correcting: small single-function files barely affect the score, while large un-decomposed files pull it toward 0. See DECISIONS.md for full rationale.

**Implementation**: When `score()` raises ValueError for < 2 categories, the CLI creates a ScoreResult with `adjusted_score=0, weight=LoC` instead of skipping.

### 3b: Hierarchical per-folder view (when running on a directory)

Group all results by folder and show per-folder LoC-weighted averages across all check types:

```
============================================================
  DIRECTORY REPORT: my_project/
  Overall: 72.3% adjusted (LoC-weighted)
============================================================
  Folder               Line    Name    File    Composite   LoC
  src/auth/            90.1%   85.3%   77.2%   84.2%       820
  src/api/             81.2%   75.0%   68.4%   74.9%       540
  src/adapters/        45.6%   52.1%   38.9%   45.5%       190
============================================================
```

This is produced by associating each `ScoreResult` with its folder path:
- line-to-function result for `src/auth/login.py` → folder `src/auth/`
- name-to-file result for `src/auth/` → folder `src/auth/`
- file-to-folder `category_scores` are already per-folder

No changes to `scorer.py` or the check classes — this is pure aggregation over existing `ScoreResult` data.

**Changes**:

`linescore/models.py`:
- `ScoreResult`: add `weight: int = 0` (LoC for this scoring unit)

`linescore/cli.py`:
- Compute LoC for each run:
  - line-to-function: `len(source.splitlines())`
  - name-to-file: sum LoC of source files in the directory
  - file-to-folder: sum LoC of all source files under the root
- When `score()` raises ValueError (< 2 categories): create a zero-score ScoreResult with weight=LoC instead of skipping
- Set `result.weight = loc` on each result

`linescore/reporting.py`:
- `format_text_summary()`: LoC-weighted overall score, LoC column in table (3a) — **DONE, needs LoC weighting update**
- New `format_folder_report()`: hierarchical per-folder view (3b) — **deferred**

**Files**: `models.py`, `reporting.py`, `cli.py`, `tests/test_reporting.py`

## Step 4: Narrow file-to-folder candidate scope to local neighborhood

**Problem**: The file-to-folder check currently uses *every* qualifying folder in the entire directory tree as candidates for every task. This conflates two different things: whether a file is well-placed within its local component, and whether it could be sorted across unrelated components. A file in `src/auth/` shouldn't need to be distinguishable from folders under `src/billing/utils/` — those are different components entirely. The check should measure local organizational quality, not global tree-wide sortability.

**Design**: For each file/subfolder being classified, restrict candidates to its **local neighborhood**:
1. **Parent folder** — the folder that actually contains the item (the correct answer)
2. **Sibling folders** — other folders at the same level (same parent)
3. **Grandparent folder** — one level up from the parent

This keeps the question meaningful: "does this item clearly belong here among its close neighbors?" If it does, the code is well-organized locally. Items in distant parts of the tree are irrelevant.

**Changes**:

`linescore/checks/file_to_folder.py` — `extract()`:
- Replace the current global `all_folders` candidate set with a per-task neighborhood computation
- For each task item with parent `P`:
  - `parent = P`
  - `siblings = [child for child in P.parent.iterdir() if child.is_dir() and not ignored]`
  - `grandparent = P.parent` (represented as its relative path, same as current convention)
  - `candidates = deduplicated union of [parent, siblings, grandparent]`
- If the neighborhood yields < 2 candidates (e.g., a top-level folder with no siblings), skip the task (same as current behavior for folders with < 2 children)

**Files**: `file_to_folder.py`, `tests/test_check_file_to_folder.py`

## Step 5: Reference scores / benchmarking

This is the validation step — does the heuristic actually identify good vs bad design?

**Architectural note**: After Steps 2-3, the library already supports running all checks on a whole directory and producing hierarchical per-folder reports. Benchmarking reuses this — it's just "run the same thing on someone else's repo and compare across repos."

`linescore/cli.py` — add `linescore benchmark` subcommand:
- Ships with a list of ~5 well-known open source Python repos (e.g., `requests`, `flask`, `black`, `httpx`, `fastapi`)
- Clones them to a temp dir
- Runs the same all-checks-on-directory flow from Step 2, reuses the folder report from Step 3
- Adds a cross-repo comparison table at the end:

```
============================================================
  BENCHMARK COMPARISON
============================================================
  Repo               Line    Name    File    Composite
  requests           81.2%   75.0%   68.4%   74.9%
  flask              72.3%   68.1%   71.0%   70.5%
  black              88.5%   82.3%   79.1%   83.3%
  ...
============================================================
```

- Stores results in `~/.linescore/benchmarks/` as JSON for future comparison

### Implementation note

This step is a follow-up. The main deliverable is steps 1-4, which give users the full hierarchical scoring experience on their own repos. Benchmarking adds the curated repo list, cloning, and cross-repo comparison on top of that.

## Implementation order

1. ~~Chance-adjusted scoring (models + scorer + reporting + tests) — with per-task k support from the start~~ **DONE**
2. ~~Multi-check `--check all` with recursive directory walking (CLI restructuring)~~ **DONE**
3. Summary + hierarchical per-folder report (reporting + CLI)
   - 3a flat summary: **partially done** — needs LoC weighting, single-category zero-scoring, LoC column
   - 3b hierarchical folder report: **deferred**
4. ~~Narrow file-to-folder candidates to local neighborhood~~ **DONE**
5. Benchmark subcommand (reuses Steps 2-3 infrastructure, optional/stretch)

Steps 1-4 are the main deliverable. Step 5 is a thin layer on top.

## Verification

- All existing 64 tests pass after each step
- New tests for adjusted scoring: verify formula with known k values (k=2: 75% raw -> 50% adjusted; k=5: 40% raw -> 25% adjusted)
- Adjusted scoring works correctly with variable k (mixed candidate set sizes)
- `linescore --help` shows `all` as default for `--check`
- `linescore .` runs all three checks recursively on the current directory
- `linescore somefile.py` runs only line-to-function
- Flat summary appears at the end of multi-target runs
- Hierarchical per-folder report appears when target is a directory
- JSON output includes `adjusted_score`, `chance_level`, `num_categories`
- file-to-folder candidates are limited to parent, siblings, and grandparent
- file-to-folder tests updated to verify neighborhood scoping
