"""Backend protocol and shared utilities for LLM backends."""

import json
from typing import Protocol

from linescore.models import JudgmentResult


class Backend(Protocol):
    """How to call an LLM. All backends implement this."""

    def complete(self, prompt: str) -> str:
        """Send a prompt to the LLM, return raw text response."""
        ...


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks (e.g., from Qwen3 reasoning models)."""
    import re
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def parse_judgment_json(text: str) -> JudgmentResult:
    """Parse a JSON response into a JudgmentResult.

    Handles multiple formats:
    - Direct JSON: {"guess": "...", "confidence": ...}
    - Claude Code wrapped: {"result": "..."}
    - Markdown-fenced JSON in result field
    - Thinking-wrapped responses (e.g., <think>...</think> from Qwen3)
    """
    text = _strip_thinking(text)

    try:
        outer = json.loads(text)
    except (json.JSONDecodeError, AttributeError, TypeError):
        outer = {}

    if "result" in outer:
        inner_text = outer["result"].strip()
    elif "guess" in outer:
        return JudgmentResult(
            guess=outer.get("guess", ""),
            confidence=float(outer.get("confidence", 0.0)),
        )
    else:
        inner_text = text.strip()

    # Strip markdown fences if present
    inner_text = inner_text.removeprefix("```json").removesuffix("```").strip()

    try:
        data = json.loads(inner_text)
        return JudgmentResult(
            guess=data.get("guess", ""),
            confidence=float(data.get("confidence", 0.0)),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return JudgmentResult(guess="", confidence=0.0)
