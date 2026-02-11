"""Backend using the Anthropic Python SDK directly."""


class AnthropicBackend:
    """Calls the Anthropic messages API via the official SDK."""

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 256,
    ):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The anthropic backend requires the anthropic package. "
                "Install it with: linescore install anthropic"
            )

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
