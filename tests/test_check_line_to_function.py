"""Tests for the line-to-function check."""

import textwrap

from linescore.checks.line_to_function import LineToFunctionCheck
from linescore.languages.python import PythonLanguage


def _source():
    return textwrap.dedent("""\
        def calculate_tax(price, rate):
            amount = price * rate
            return amount

        def send_email(to, subject):
            msg = build_message(to, subject)
            smtp.send(msg)
    """)


class TestLineToFunctionCheck:
    def setup_method(self):
        self.check = LineToFunctionCheck(PythonLanguage())

    def test_extracts_tasks(self):
        tasks = self.check.extract(_source())
        assert len(tasks) > 0
        for t in tasks:
            assert t.actual in ("calculate_tax", "send_email")
            assert set(t.candidates) == {"calculate_tax", "send_email"}

    def test_items_are_statements(self):
        tasks = self.check.extract(_source())
        items = [t.item for t in tasks]
        assert any("price * rate" in item for item in items)
        assert any("build_message" in item for item in items)

    def test_too_few_functions_returns_empty(self):
        source = "def only_one():\n    x = 1\n"
        assert self.check.extract(source) == []

    def test_build_prompt_contains_candidates_and_item(self):
        prompt = self.check.build_prompt(["foo", "bar"], "x = compute()")
        assert "foo" in prompt
        assert "bar" in prompt
        assert "x = compute()" in prompt
