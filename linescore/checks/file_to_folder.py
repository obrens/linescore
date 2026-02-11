"""Check: can the LLM guess which folder a file/subfolder belongs to?"""

from pathlib import Path

from linescore.models import ClassificationTask


_PROMPT_TEMPLATE = """\
You are a code analysis tool. You will be given:
1. A list of folder names from a project directory tree.
2. A single file or subfolder name from one of those folders.

Your task: guess which folder the item most likely belongs to.

Respond with ONLY a JSON object: {{"guess": "<folder_name>", "confidence": <0.0-1.0>}}
No other text.

Folders:
{folder_list}

Item:
  {item}

Which folder does this item belong to?"""


class FileToFolderCheck:
    """Score how identifiable each file/subfolder is within its parent folder."""

    name = "file-to-folder"

    def extract(self, target: str) -> list[ClassificationTask]:
        """Extract classification tasks from a directory tree.

        Args:
            target: Path to a root directory to walk.
        """
        root = Path(target)
        if not root.is_dir():
            return []

        # Collect children per folder (only folders that have 2+ non-hidden children)
        folder_children: dict[str, list[str]] = {}
        def _skip(p: Path) -> bool:
            return any(part.startswith(".") or part == "__pycache__" for part in p.relative_to(root).parts)

        for dirpath in sorted(root.rglob("*")):
            if not dirpath.is_dir() or _skip(dirpath):
                continue
            children = [
                p.name for p in sorted(dirpath.iterdir())
                if not p.name.startswith(".")
                and p.name != "__pycache__"
                and not p.name.endswith(".pyc")
            ]
            if len(children) >= 2:
                folder_children[str(dirpath.relative_to(root))] = children

        # Also check root itself
        root_children = [
            p.name for p in sorted(root.iterdir())
            if not p.name.startswith(".")
            and p.name != "__pycache__"
            and not p.name.endswith(".pyc")
        ]
        if len(root_children) >= 2:
            folder_children["."] = root_children

        if len(folder_children) < 2:
            return []

        all_folders = list(folder_children.keys())
        tasks = []
        for folder, children in folder_children.items():
            for child in children:
                tasks.append(ClassificationTask(
                    item=child,
                    actual=folder,
                    candidates=all_folders,
                ))
        return tasks

    def build_prompt(self, candidates: list[str], item: str) -> str:
        folder_list = "\n".join(f"  - {f}" for f in candidates)
        return _PROMPT_TEMPLATE.format(folder_list=folder_list, item=item)
