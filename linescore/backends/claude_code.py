"""Backend that shells out to the `claude` CLI."""

import subprocess


class ClaudeCodeBackend:
    """Calls the `claude` CLI tool as a subprocess."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001", timeout: int = 30):
        self._model = model
        self._timeout = timeout

    def complete(self, prompt: str) -> str:
        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--output-format", "json", "--model", self._model],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return ""

        if result.returncode != 0:
            return ""

        return result.stdout
