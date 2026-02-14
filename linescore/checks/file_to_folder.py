"""Check: can the LLM guess which folder a file/subfolder belongs to?"""

from pathlib import Path

from linescore.languages import Language
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

    def __init__(self, language: Language):
        self._language = language

    def _should_ignore(self, name: str) -> bool:
        if name.startswith("."):
            return True
        if name in self._language.ignore_dirs:
            return True
        if any(name.endswith(s) for s in self._language.ignore_suffixes):
            return True
        return False

    def _neighborhood(self, folder_rel: str, root: Path) -> list[str]:
        """Get candidate folders in the local neighborhood of a folder.

        For a folder F, the neighborhood is:
        - F itself
        - Sibling folders (other folders at the same level as F)
        - The parent of F (one level up)

        For the root folder ".", the neighborhood is root + its direct
        child folders (since root has no siblings or parent).
        """
        if folder_rel == ".":
            # Root: candidates are root + its direct child folders
            candidates = {"."}
            for p in root.iterdir():
                if p.is_dir() and not self._should_ignore(p.name):
                    candidates.add(str(p.relative_to(root)))
            return sorted(candidates)

        folder_path = Path(folder_rel)
        parent_path = folder_path.parent
        parent_rel = str(parent_path) if str(parent_path) != "." else "."
        parent_abs = root if parent_rel == "." else root / parent_rel

        # Sibling folders (including folder_rel itself)
        candidates: set[str] = set()
        for p in parent_abs.iterdir():
            if p.is_dir() and not self._should_ignore(p.name):
                candidates.add(str(p.relative_to(root)))

        # Also include the parent folder
        candidates.add(parent_rel)

        return sorted(candidates)

    def extract(self, target: str) -> list[ClassificationTask]:
        """Extract classification tasks from a directory tree.

        Each item is classified among its local neighborhood: its parent
        folder, sibling folders, and grandparent folder.

        Args:
            target: Path to a root directory to walk.
        """
        root = Path(target)
        if not root.is_dir():
            return []

        ignore_dirs = self._language.ignore_dirs

        def _skip_dir(p: Path) -> bool:
            return any(
                part.startswith(".") or part in ignore_dirs
                for part in p.relative_to(root).parts
            )

        # Collect children per folder (only folders that have 2+ non-ignored children)
        folder_children: dict[str, list[str]] = {}
        for dirpath in sorted(root.rglob("*")):
            if not dirpath.is_dir() or _skip_dir(dirpath):
                continue
            children = [
                p.name for p in sorted(dirpath.iterdir())
                if not self._should_ignore(p.name)
            ]
            if len(children) >= 2:
                folder_children[str(dirpath.relative_to(root))] = children

        # Also check root itself
        root_children = [
            p.name for p in sorted(root.iterdir())
            if not self._should_ignore(p.name)
        ]
        if len(root_children) >= 2:
            folder_children["."] = root_children

        tasks = []
        for folder, children in folder_children.items():
            candidates = self._neighborhood(folder, root)
            if len(candidates) < 2:
                continue
            for child in children:
                tasks.append(ClassificationTask(
                    item=child,
                    actual=folder,
                    candidates=candidates,
                ))
        return tasks

    def build_prompt(self, candidates: list[str], item: str) -> str:
        folder_list = "\n".join(f"  - {f}" for f in candidates)
        return _PROMPT_TEMPLATE.format(folder_list=folder_list, item=item)
