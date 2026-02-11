"""Check: can the LLM guess which function a code line belongs to?"""

from linescore.languages import Language
from linescore.models import ClassificationTask


_PROMPT_TEMPLATE = """\
You are a code analysis tool. You will be given:
1. A list of function names from a source module.
2. A single statement of code pulled from one of those functions.

Your task: guess which function the statement most likely belongs to.

Respond with ONLY a JSON object: {{"guess": "<function_name>", "confidence": <0.0-1.0>}}
No other text.

Function names in this module:
{names_list}

Statement:
```
{statement}
```

Which function does this statement belong to?"""


class LineToFunctionCheck:
    """Score how identifiable each line of code is within its function."""

    name = "line-to-function"

    def __init__(self, language: Language):
        self._language = language

    def extract(self, target: str) -> list[ClassificationTask]:
        """Extract classification tasks from source code.

        Args:
            target: Source code string.
        """
        functions = self._language.extract_functions(target)
        if len(functions) < 2:
            return []

        all_names = [f.name for f in functions]
        tasks = []
        for func in functions:
            for stmt in func.statements:
                tasks.append(ClassificationTask(
                    item=stmt,
                    actual=func.name,
                    candidates=all_names,
                ))
        return tasks

    def build_prompt(self, candidates: list[str], item: str) -> str:
        names_list = "\n".join(f"  - {n}" for n in candidates)
        return _PROMPT_TEMPLATE.format(names_list=names_list, statement=item)
