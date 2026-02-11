import textwrap

import pytest

from linescore.models import FunctionInfo, JudgmentResult
from linescore.scorer import score_module


class FakeParser:
    """Parser that returns pre-defined functions."""

    def __init__(self, functions: list[FunctionInfo]):
        self._functions = functions

    def extract_functions(self, source: str) -> list[FunctionInfo]:
        return self._functions


class PerfectJudge:
    """Judge that always guesses correctly."""

    def __init__(self):
        self.calls: list[tuple[list[str], str]] = []

    def judge(self, function_names: list[str], statement: str) -> JudgmentResult:
        self.calls.append((function_names, statement))
        # Cheat: the statement contains the function name
        for name in function_names:
            if name in statement:
                return JudgmentResult(guess=name, confidence=1.0)
        return JudgmentResult(guess=function_names[0], confidence=0.5)


class WrongJudge:
    """Judge that always guesses the wrong function."""

    def judge(self, function_names: list[str], statement: str) -> JudgmentResult:
        # Always guess the first function that ISN'T in the statement
        for name in function_names:
            if name not in statement:
                return JudgmentResult(guess=name, confidence=0.8)
        return JudgmentResult(guess="unknown", confidence=0.1)


def _make_functions() -> list[FunctionInfo]:
    return [
        FunctionInfo(name="calculate_tax", statements=[
            "calculate_tax: rate = get_tax_rate()",
            "calculate_tax: amount = price * rate",
        ]),
        FunctionInfo(name="send_email", statements=[
            "send_email: msg = build_message(to, subject)",
            "send_email: smtp.send(msg)",
        ]),
    ]


class TestScoreModule:
    def test_perfect_score(self):
        functions = _make_functions()
        parser = FakeParser(functions)
        judge = PerfectJudge()

        result = score_module("ignored", parser, judge, workers=1)

        assert result.score == 1.0
        assert result.correct == 4
        assert result.total == 4
        assert len(result.line_results) == 4
        assert all(r.correct for r in result.line_results)

    def test_zero_score(self):
        functions = _make_functions()
        parser = FakeParser(functions)
        judge = WrongJudge()

        result = score_module("ignored", parser, judge, workers=1)

        assert result.score == 0.0
        assert result.correct == 0
        assert result.total == 4

    def test_too_few_functions_raises(self):
        parser = FakeParser([
            FunctionInfo(name="only_one", statements=["x = 1"]),
        ])
        judge = PerfectJudge()

        with pytest.raises(ValueError, match="at least 2 functions"):
            score_module("ignored", parser, judge)

    def test_max_statements_sampling(self):
        functions = _make_functions()
        parser = FakeParser(functions)
        judge = PerfectJudge()

        result = score_module("ignored", parser, judge, max_statements=2, workers=1)

        assert result.total == 2
        assert len(result.line_results) == 2

    def test_function_scores_computed(self):
        functions = _make_functions()
        parser = FakeParser(functions)
        judge = PerfectJudge()

        result = score_module("ignored", parser, judge, workers=1)

        assert len(result.function_scores) == 2
        for fs in result.function_scores:
            assert fs.score == 1.0

    def test_confused_pairs_populated_on_wrong_guesses(self):
        functions = _make_functions()
        parser = FakeParser(functions)
        judge = WrongJudge()

        result = score_module("ignored", parser, judge, workers=1)

        assert len(result.confused_pairs) > 0

    def test_on_result_callback_called(self):
        functions = _make_functions()
        parser = FakeParser(functions)
        judge = PerfectJudge()

        calls = []
        def callback(lr, completed, total):
            calls.append((completed, total))

        score_module("ignored", parser, judge, workers=1, on_result=callback)

        assert len(calls) == 4
        # All calls should have total=4
        assert all(t == 4 for _, t in calls)
        # completed counts should include 1..4
        completed_values = sorted(c for c, _ in calls)
        assert completed_values == [1, 2, 3, 4]

    def test_judge_receives_all_function_names(self):
        functions = _make_functions()
        parser = FakeParser(functions)
        judge = PerfectJudge()

        score_module("ignored", parser, judge, workers=1)

        # Every call should receive both function names
        for names, _ in judge.calls:
            assert "calculate_tax" in names
            assert "send_email" in names
