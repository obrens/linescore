import json

from linescore.models import (
    ConfusedPair,
    CategoryScore,
    GuessResult,
    ScoreResult,
)
from linescore.reporting import format_text_report, format_json


def _make_result() -> ScoreResult:
    return ScoreResult(
        score=0.75,
        total=4,
        correct=3,
        function_scores=[
            CategoryScore(name="foo", total=2, correct=2, score=1.0),
            CategoryScore(name="bar", total=2, correct=1, score=0.5),
        ],
        confused_pairs=[
            ConfusedPair(function_a="bar", function_b="foo", count=1),
        ],
        line_results=[
            GuessResult("x = 1", "foo", "foo", 0.9, True),
            GuessResult("y = calc()", "foo", "foo", 0.8, True),
            GuessResult("z = process()", "bar", "bar", 0.7, True),
            GuessResult("w = compute()", "bar", "foo", 0.6, False),
        ],
    )


class TestTextReport:
    def test_contains_score(self):
        report = format_text_report(_make_result())
        assert "75.0%" in report
        assert "3/4" in report

    def test_contains_file_path(self):
        report = format_text_report(_make_result(), file_path="my_module.py")
        assert "my_module.py" in report

    def test_contains_per_function_breakdown(self):
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

    def test_includes_function_scores(self):
        output = format_json(_make_result())
        data = json.loads(output)
        assert len(data["function_scores"]) == 2

    def test_includes_confused_pairs(self):
        output = format_json(_make_result())
        data = json.loads(output)
        assert len(data["confused_pairs"]) == 1
        assert data["confused_pairs"][0]["function_a"] == "bar"
