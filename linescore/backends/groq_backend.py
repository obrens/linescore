# linescore/backends/groq.py
"""Backend using the Groq Python SDK directly."""


class GroqBackend:
    """Calls the Groq API via the official SDK."""

    def __init__(
        self,
        model: str = "qwen/qwen3-32b",
        max_tokens: int = 256,
    ):
        try:
            import groq
        except ImportError:
            raise ImportError(
                "The groq backend requires the groq package. "
                "Install it with: linescore install groq"
            )

        self._client = groq.Groq()  # Automatically reads GROQ_API_KEY
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            reasoning_effort="none",
            messages=[{"role": "user", "content": prompt}],  # type: ignore[arg-type]
        )
        return response.choices[0].message.content