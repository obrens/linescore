import pytest

from linescore.models import ClassificationTask, JudgmentResult
from linescore.scorer import score


class FakeCheck:
    """Check that returns pre-defined tasks."""

    name = "fake-check"

    def __init__(self, tasks: list[ClassificationTask]):
        self._tasks = tasks

    def extract(self, target: str) -> list[ClassificationTask]:
        return self._tasks

    def build_prompt(self, candidates: list[str], item: str) -> str:
        return f"classify {item} among {candidates}"


class PerfectBackend:
    """Backend that always returns the correct guess (item contains the answer)."""

    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        # Extract item from "classify <item> among [...]"
        # The item is embedded in the prompt by FakeCheck
        # We cheat: return the first candidate that appears in the prompt
        # For our test data, the item contains the category name
        import json
        # Parse candidates from the prompt format "classify <item> among ['a', 'b']"
        parts = prompt.split(" among ")
        item = parts[0].removeprefix("classify ")
        candidates = eval(parts[1])
        for c in candidates:
            if c in item:
                return json.dumps({"guess": c, "confidence": 1.0})
        return json.dumps({"guess": candidates[0], "confidence": 0.5})


class WrongBackend:
    """Backend that always returns the wrong guess."""

    def complete(self, prompt: str) -> str:
        import json
        parts = prompt.split(" among ")
        item = parts[0].removeprefix("classify ")
        candidates = eval(parts[1])
        for c in candidates:
            if c not in item:
                return json.dumps({"guess": c, "confidence": 0.8})
        return json.dumps({"guess": "unknown", "confidence": 0.1})


def _make_tasks() -> list[ClassificationTask]:
    return [
        ClassificationTask(
            item="calculate_tax: rate = get_tax_rate()",
            actual="calculate_tax",
            candidates=["calculate_tax", "send_email"],
        ),
        ClassificationTask(
            item="calculate_tax: amount = price * rate",
            actual="calculate_tax",
            candidates=["calculate_tax", "send_email"],
        ),
        ClassificationTask(
            item="send_email: msg = build_message(to, subject)",
            actual="send_email",
            candidates=["calculate_tax", "send_email"],
        ),
        ClassificationTask(
            item="send_email: smtp.send(msg)",
            actual="send_email",
            candidates=["calculate_tax", "send_email"],
        ),
    ]


class TestScore:
    def test_perfect_score(self):
        check = FakeCheck(_make_tasks())
        backend = PerfectBackend()

        result = score(check, backend, "ignored", workers=1)

        assert result.score == 1.0
        assert result.correct == 4
        assert result.total == 4
        assert len(result.line_results) == 4
        assert all(r.correct for r in result.line_results)

    def test_zero_score(self):
        check = FakeCheck(_make_tasks())
        backend = WrongBackend()

        result = score(check, backend, "ignored", workers=1)

        assert result.score == 0.0
        assert result.correct == 0
        assert result.total == 4

    def test_empty_tasks_raises(self):
        check = FakeCheck([])
        backend = PerfectBackend()

        with pytest.raises(ValueError, match="No classification tasks"):
            score(check, backend, "ignored")

    def test_single_category_raises(self):
        check = FakeCheck([
            ClassificationTask(item="x = 1", actual="only_one", candidates=["only_one"]),
        ])
        backend = PerfectBackend()

        with pytest.raises(ValueError, match="at least 2 categories"):
            score(check, backend, "ignored")

    def test_max_items_sampling(self):
        check = FakeCheck(_make_tasks())
        backend = PerfectBackend()

        result = score(check, backend, "ignored", max_items=2, workers=1)

        assert result.total == 2
        assert len(result.line_results) == 2

    def test_category_scores_computed(self):
        check = FakeCheck(_make_tasks())
        backend = PerfectBackend()

        result = score(check, backend, "ignored", workers=1)

        assert len(result.function_scores) == 2
        for fs in result.function_scores:
            assert fs.score == 1.0

    def test_confused_pairs_populated_on_wrong_guesses(self):
        check = FakeCheck(_make_tasks())
        backend = WrongBackend()

        result = score(check, backend, "ignored", workers=1)

        assert len(result.confused_pairs) > 0

    def test_on_result_callback_called(self):
        check = FakeCheck(_make_tasks())
        backend = PerfectBackend()

        calls = []
        def callback(lr, completed, total):
            calls.append((completed, total))

        score(check, backend, "ignored", workers=1, on_result=callback)

        assert len(calls) == 4
        assert all(t == 4 for _, t in calls)
        completed_values = sorted(c for c, _ in calls)
        assert completed_values == [1, 2, 3, 4]

    def test_check_name_in_result(self):
        check = FakeCheck(_make_tasks())
        backend = PerfectBackend()

        result = score(check, backend, "ignored", workers=1)

        assert result.check == "fake-check"
