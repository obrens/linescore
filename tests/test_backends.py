"""Tests for backends: shared parser + each backend with mocks."""

from unittest.mock import patch, MagicMock

from linescore.backends import parse_judgment_json
from linescore.backends.claude_code import ClaudeCodeBackend


class TestParseJudgmentJson:
    def test_direct_json(self):
        r = parse_judgment_json('{"guess": "foo", "confidence": 0.9}')
        assert r.guess == "foo"
        assert r.confidence == 0.9

    def test_wrapped_json(self):
        r = parse_judgment_json('{"result": "{\\"guess\\": \\"bar\\", \\"confidence\\": 0.7}"}')
        assert r.guess == "bar"
        assert r.confidence == 0.7

    def test_markdown_fenced(self):
        r = parse_judgment_json('{"result": "```json\\n{\\"guess\\": \\"baz\\", \\"confidence\\": 0.5}\\n```"}')
        assert r.guess == "baz"
        assert r.confidence == 0.5

    def test_garbage_returns_empty(self):
        r = parse_judgment_json("not json at all")
        assert r.guess == ""
        assert r.confidence == 0.0

    def test_empty_string(self):
        r = parse_judgment_json("")
        assert r.guess == ""
        assert r.confidence == 0.0

    def test_missing_fields(self):
        r = parse_judgment_json('{"result": "{\\"other\\": \\"value\\"}"}')
        assert r.guess == ""
        assert r.confidence == 0.0


class TestClaudeCodeBackend:
    @patch("linescore.backends.claude_code.subprocess.run")
    def test_returns_stdout_on_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"result": "{\\"guess\\": \\"foo\\", \\"confidence\\": 0.9}"}',
        )
        backend = ClaudeCodeBackend()
        result = backend.complete("test prompt")
        assert "foo" in result

    @patch("linescore.backends.claude_code.subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        backend = ClaudeCodeBackend()
        assert backend.complete("test") == ""

    @patch("linescore.backends.claude_code.subprocess.run")
    def test_returns_empty_on_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=30)
        backend = ClaudeCodeBackend()
        assert backend.complete("test") == ""

    @patch("linescore.backends.claude_code.subprocess.run")
    def test_passes_prompt_and_model(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="{}")
        backend = ClaudeCodeBackend(model="claude-sonnet-4-5-20250929")
        backend.complete("my prompt")
        args = mock_run.call_args[0][0]
        assert "my prompt" in args
        assert "claude-sonnet-4-5-20250929" in args


class TestAnthropicBackend:
    @patch.dict("sys.modules", {"anthropic": MagicMock()})
    def test_calls_messages_create(self):
        import sys
        mock_anthropic = sys.modules["anthropic"]
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"guess": "foo", "confidence": 0.8}')]
        mock_client.messages.create.return_value = mock_response

        from linescore.backends.anthropic import AnthropicBackend
        backend = AnthropicBackend.__new__(AnthropicBackend)
        backend._client = mock_client
        backend._model = "claude-haiku-4-5-20251001"
        backend._max_tokens = 256

        result = backend.complete("test prompt")
        assert "foo" in result
        mock_client.messages.create.assert_called_once()


class TestLlamaCppBackend:
    def test_calls_llama(self):
        mock_llm = MagicMock()
        mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": '{"guess": "bar", "confidence": 0.6}'}}]
        }

        from linescore.backends.llamacpp import LlamaCppBackend
        backend = LlamaCppBackend.__new__(LlamaCppBackend)
        backend._llm = mock_llm
        backend._max_tokens = 256
        backend._n_ctx = 8192
        backend._lock = __import__("threading").Lock()

        result = backend.complete("test prompt")
        assert "bar" in result
        mock_llm.create_chat_completion.assert_called_once()
