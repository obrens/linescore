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
        import json
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
        assert len(result.results) == 4
        assert all(r.correct for r in result.results)

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
        assert len(result.results) == 2

    def test_category_scores_computed(self):
        check = FakeCheck(_make_tasks())
        backend = PerfectBackend()

        result = score(check, backend, "ignored", workers=1)

        assert len(result.category_scores) == 2
        for cs in result.category_scores:
            assert cs.score == 1.0

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

    def test_adjusted_score_perfect_k2(self):
        """Perfect score with k=2: adjusted should be 1.0."""
        check = FakeCheck(_make_tasks())  # k=2 (2 candidates)
        backend = PerfectBackend()

        result = score(check, backend, "ignored", workers=1)

        assert result.adjusted_score == pytest.approx(1.0)
        assert result.chance_level == pytest.approx(0.5)
        assert result.num_categories == 2

    def test_adjusted_score_zero_k2(self):
        """All wrong with k=2: adjusted should be -1.0."""
        check = FakeCheck(_make_tasks())
        backend = WrongBackend()

        result = score(check, backend, "ignored", workers=1)

        # adjusted = (0 - 0.5) / (1 - 0.5) = -1.0
        assert result.adjusted_score == pytest.approx(-1.0)

    def test_adjusted_score_k5(self):
        """With k=5, 40% raw -> 25% adjusted."""
        candidates = ["a", "b", "c", "d", "e"]
        tasks = [
            ClassificationTask(item=f"a: item{i}", actual="a", candidates=candidates)
            for i in range(2)
        ] + [
            ClassificationTask(item=f"b: item{i}", actual="b", candidates=candidates)
            for i in range(3)
        ] + [
            ClassificationTask(item=f"c: item{i}", actual="c", candidates=candidates)
            for i in range(5)
        ]  # 10 tasks total
        check = FakeCheck(tasks)
        backend = PerfectBackend()

        result = score(check, backend, "ignored", workers=1)

        # chance = 1/5 = 0.2, raw = 1.0, adjusted = (1.0 - 0.2) / (1 - 0.2) = 1.0
        assert result.chance_level == pytest.approx(0.2)
        assert result.adjusted_score == pytest.approx(1.0)
        assert result.num_categories == 5

    def test_adjusted_score_mixed_k(self):
        """Tasks with different candidate set sizes compute per-task adjustment."""
        tasks = [
            # k=2 task, will be correct
            ClassificationTask(item="a: line1", actual="a", candidates=["a", "b"]),
            # k=4 task, will be correct
            ClassificationTask(item="a: line2", actual="a", candidates=["a", "b", "c", "d"]),
        ]
        check = FakeCheck(tasks)
        backend = PerfectBackend()

        result = score(check, backend, "ignored", workers=1)

        # Task 1: adj = (1 - 0.5) / (1 - 0.5) = 1.0
        # Task 2: adj = (1 - 0.25) / (1 - 0.25) = 1.0
        # Mean = 1.0
        assert result.adjusted_score == pytest.approx(1.0)
        # Chance = mean(0.5, 0.25) = 0.375
        assert result.chance_level == pytest.approx(0.375)

    def test_num_candidates_recorded(self):
        check = FakeCheck(_make_tasks())
        backend = PerfectBackend()

        result = score(check, backend, "ignored", workers=1)

        for r in result.results:
            assert r.num_candidates == 2
