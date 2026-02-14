import json

from linescore.models import (
    ConfusedPair,
    CategoryScore,
    GuessResult,
    ScoreResult,
)
from linescore.reporting import format_text_report, format_text_summary, format_json


def _make_result() -> ScoreResult:
    return ScoreResult(
        score=0.75,
        total=4,
        correct=3,
        check="line-to-function",
        adjusted_score=0.5,
        chance_level=0.5,
        num_categories=2,
        category_scores=[
            CategoryScore(name="foo", total=2, correct=2, score=1.0),
            CategoryScore(name="bar", total=2, correct=1, score=0.5),
        ],
        confused_pairs=[
            ConfusedPair(category_a="bar", category_b="foo", count=1),
        ],
        results=[
            GuessResult("x = 1", "foo", "foo", 0.9, True, num_candidates=2),
            GuessResult("y = calc()", "foo", "foo", 0.8, True, num_candidates=2),
            GuessResult("z = process()", "bar", "bar", 0.7, True, num_candidates=2),
            GuessResult("w = compute()", "bar", "foo", 0.6, False, num_candidates=2),
        ],
    )


class TestTextReport:
    def test_contains_score(self):
        report = format_text_report(_make_result())
        assert "50.0% adjusted" in report
        assert "75.0% raw" in report
        assert "3/4" in report
        assert "chance=50.0%" in report

    def test_contains_file_path(self):
        report = format_text_report(_make_result(), file_path="my_module.py")
        assert "my_module.py" in report

    def test_contains_per_category_breakdown(self):
        report = format_text_report(_make_result())
        assert "foo" in report
        assert "bar" in report

    def test_contains_wrong_guesses(self):
        report = format_text_report(_make_result())
        assert "w = compute()" in report
        assert "decomposition issues" in report

    def test_contains_confused_pairs(self):
        report = format_text_report(_make_result())
        assert "confused" in report.lower()
        assert "bar" in report
        assert "1 mismatches" in report

    def test_check_specific_labels(self):
        result = _make_result()
        report = format_text_report(result)
        assert "Per-function breakdown:" in report

        result.check = "name-to-file"
        report = format_text_report(result)
        assert "Per-file breakdown:" in report

        result.check = "file-to-folder"
        report = format_text_report(result)
        assert "Per-folder breakdown:" in report


class TestJsonReport:
    def test_valid_json(self):
        output = format_json(_make_result())
        data = json.loads(output)
        assert data["score"] == 0.75
        assert data["total"] == 4

    def test_includes_file_path(self):
        output = format_json(_make_result(), file_path="test.py")
        data = json.loads(output)
        assert data["file"] == "test.py"

    def test_includes_category_scores(self):
        output = format_json(_make_result())
        data = json.loads(output)
        assert len(data["category_scores"]) == 2

    def test_includes_confused_pairs(self):
        output = format_json(_make_result())
        data = json.loads(output)
        assert len(data["confused_pairs"]) == 1
        assert data["confused_pairs"][0]["category_a"] == "bar"

    def test_includes_adjusted_score(self):
        output = format_json(_make_result())
        data = json.loads(output)
        assert data["adjusted_score"] == 0.5
        assert data["chance_level"] == 0.5
        assert data["num_categories"] == 2
        assert "weight" in data


class TestTextSummary:
    def test_shows_all_runs(self):
        r1 = ScoreResult(score=0.75, total=4, correct=3, check="line-to-function",
                         adjusted_score=0.5, chance_level=0.5, num_categories=2, weight=100)
        r2 = ScoreResult(score=0.80, total=5, correct=4, check="name-to-file",
                         adjusted_score=0.6, chance_level=0.5, num_categories=2, weight=200)
        summary = format_text_summary([
            ("line-to-function", "email.py", r1),
            ("name-to-file", "src/", r2),
        ])
        assert "email.py" in summary
        assert "src/" in summary
        assert "line-to-function" in summary
        assert "name-to-file" in summary

    def test_loc_weighted_overall(self):
        # r1: adj=0.4, 100 LoC.  r2: adj=0.8, 300 LoC.
        # weighted = (0.4*100 + 0.8*300) / (100+300) = (40+240)/400 = 0.7
        r1 = ScoreResult(score=0.75, total=4, correct=3, check="line-to-function",
                         adjusted_score=0.4, chance_level=0.5, num_categories=2, weight=100)
        r2 = ScoreResult(score=0.80, total=5, correct=4, check="name-to-file",
                         adjusted_score=0.8, chance_level=0.5, num_categories=2, weight=300)
        summary = format_text_summary([
            ("line-to-function", "a.py", r1),
            ("name-to-file", "src/", r2),
        ])
        assert "70.0%" in summary
        assert "Overall" in summary
        assert "LoC-weighted" in summary

    def test_equal_weight_fallback_when_no_loc(self):
        # No LoC set (weight=0) — falls back to equal averaging
        r1 = ScoreResult(score=0.75, total=4, correct=3, check="x",
                         adjusted_score=0.4, chance_level=0.5, num_categories=2)
        r2 = ScoreResult(score=0.80, total=5, correct=4, check="x",
                         adjusted_score=0.6, chance_level=0.5, num_categories=2)
        summary = format_text_summary([("x", "a", r1), ("x", "b", r2)])
        # Equal mean of 0.4 and 0.6 = 0.5
        assert "50.0%" in summary

    def test_shows_run_count_and_loc(self):
        r = ScoreResult(score=0.5, total=2, correct=1, check="x",
                        adjusted_score=0.0, chance_level=0.5, num_categories=2, weight=50)
        summary = format_text_summary([("x", "a", r), ("x", "b", r), ("x", "c", r)])
        assert "3 runs" in summary
        assert "150 LoC" in summary

    def test_shows_loc_per_run(self):
        r = ScoreResult(score=0.5, total=2, correct=1, check="x",
                        adjusted_score=0.0, chance_level=0.5, num_categories=2, weight=120)
        summary = format_text_summary([("x", "a", r), ("x", "b", r)])
        assert "120" in summary

    def test_truncates_long_labels(self):
        r = ScoreResult(score=0.5, total=2, correct=1, check="x",
                        adjusted_score=0.0, chance_level=0.5, num_categories=2, weight=10)
        long_label = "a" * 100
        summary = format_text_summary([("x", long_label, r), ("x", "b", r)])
        assert "..." in summary
