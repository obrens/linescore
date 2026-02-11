import json
import subprocess

from linescore.models import JudgmentResult


_PROMPT_TEMPLATE = """\
You are a code analysis tool. You will be given:
1. A list of function names from a Python module.
2. A single statement of code pulled from one of those functions.

Your task: guess which function the statement most likely belongs to.

Respond with ONLY a JSON object: {{"guess": "<function_name>", "confidence": <0.0-1.0>}}
No other text.

Function names in this module:
{names_list}

Statement:
```python
{statement}
```

Which function does this statement belong to?"""


class ClaudeCodeJudge:
    """Judge that shells out to the `claude` CLI."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001", timeout: int = 30):
        self._model = model
        self._timeout = timeout

    def judge(self, function_names: list[str], statement: str) -> JudgmentResult:
        names_list = "\n".join(f"  - {n}" for n in function_names)
        prompt = _PROMPT_TEMPLATE.format(names_list=names_list, statement=statement)

        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--output-format", "json", "--model", self._model],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return JudgmentResult(guess="", confidence=0.0)

        if result.returncode != 0:
            return JudgmentResult(guess="", confidence=0.0)

        return self._parse_response(result.stdout)

    @staticmethod
    def _parse_response(stdout: str) -> JudgmentResult:
        # Claude Code with --output-format json wraps the response in {"result": "..."}
        # But we also handle the case where it returns raw JSON directly.
        try:
            outer = json.loads(stdout)
        except (json.JSONDecodeError, AttributeError):
            outer = {}

        if "result" in outer:
            text = outer["result"].strip()
        elif "guess" in outer:
            # Direct JSON response with the fields we need
            return JudgmentResult(
                guess=outer.get("guess", ""),
                confidence=float(outer.get("confidence", 0.0)),
            )
        else:
            text = stdout.strip()

        # Strip markdown fences if present
        text = text.removeprefix("```json").removesuffix("```").strip()

        try:
            data = json.loads(text)
            return JudgmentResult(
                guess=data.get("guess", ""),
                confidence=float(data.get("confidence", 0.0)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return JudgmentResult(guess="", confidence=0.0)
