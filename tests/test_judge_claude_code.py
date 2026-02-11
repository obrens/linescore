"""Tests for ClaudeCodeJudge response parsing (no actual subprocess calls)."""

from linescore.judges.claude_code import ClaudeCodeJudge


class TestParseResponse:
    def test_parses_wrapped_json_response(self):
        stdout = '{"result": "{\\"guess\\": \\"foo\\", \\"confidence\\": 0.9}"}'
        result = ClaudeCodeJudge._parse_response(stdout)
        assert result.guess == "foo"
        assert result.confidence == 0.9

    def test_parses_direct_json_response(self):
        stdout = '{"guess": "bar", "confidence": 0.75}'
        result = ClaudeCodeJudge._parse_response(stdout)
        assert result.guess == "bar"
        assert result.confidence == 0.75

    def test_parses_markdown_fenced_json(self):
        stdout = '{"result": "```json\\n{\\"guess\\": \\"baz\\", \\"confidence\\": 0.5}\\n```"}'
        result = ClaudeCodeJudge._parse_response(stdout)
        assert result.guess == "baz"
        assert result.confidence == 0.5

    def test_returns_empty_on_garbage(self):
        result = ClaudeCodeJudge._parse_response("not json at all")
        assert result.guess == ""
        assert result.confidence == 0.0

    def test_returns_empty_on_empty_string(self):
        result = ClaudeCodeJudge._parse_response("")
        assert result.guess == ""
        assert result.confidence == 0.0

    def test_handles_missing_fields(self):
        stdout = '{"result": "{\\"other\\": \\"value\\"}"}'
        result = ClaudeCodeJudge._parse_response(stdout)
        assert result.guess == ""
        assert result.confidence == 0.0
