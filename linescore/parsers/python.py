import ast

from linescore.models import FunctionInfo


class _StatementExtractor(ast.NodeVisitor):
    """Walk a function body and collect individual statements as source lines."""

    _SKIP_TYPES = (
        ast.FunctionDef, ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Import, ast.ImportFrom,
        ast.Pass, ast.Break, ast.Continue,
    )

    def __init__(self, source_lines: list[str]):
        self._source_lines = source_lines
        self.statements: list[str] = []

    def _get_source(self, node: ast.AST) -> str | None:
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        raw = self._source_lines[start:end]
        text = "\n".join(raw).strip()
        return text if text else None

    def _is_trivial(self, text: str) -> bool:
        stripped = text.strip()
        if stripped in ("return", "return None", "else:", "finally:", "", "..."):
            return True
        # self.x = x style (simple constructor forwarding)
        if stripped.startswith("self.") and stripped.count("=") == 1:
            lhs, rhs = stripped.split("=", 1)
            attr = lhs.strip().removeprefix("self.").strip()
            if attr == rhs.strip():
                return True
        return False

    # Compound statement types and their body-list attributes
    _COMPOUND_BODIES: dict[type, list[str]] = {
        ast.If: ["body", "orelse"],
        ast.For: ["body", "orelse"],
        ast.AsyncFor: ["body", "orelse"],
        ast.While: ["body", "orelse"],
        ast.With: ["body"],
        ast.AsyncWith: ["body"],
        ast.Try: ["body", "handlers", "orelse", "finalbody"],
        ast.ExceptHandler: ["body"],
    }

    def _visit_stmt(self, node: ast.AST):
        if isinstance(node, self._SKIP_TYPES):
            return

        # Compound statements: collect header, recurse into body lists only
        body_attrs = self._COMPOUND_BODIES.get(type(node))
        if body_attrs is not None:
            header = self._source_lines[node.lineno - 1].strip()
            if header and not self._is_trivial(header):
                self.statements.append(header)
            for attr in body_attrs:
                for child in getattr(node, attr, []):
                    self._visit_stmt(child)
            return

        # Leaf statements
        src = self._get_source(node)
        if src and not self._is_trivial(src):
            self.statements.append(src)

    def extract_from_body(self, body: list[ast.stmt]) -> list[str]:
        for node in body:
            self._visit_stmt(node)
        return self.statements


class _ParentMapper(ast.NodeVisitor):
    """Single-pass visitor that maps each node to its parent."""

    def __init__(self):
        self.parent: dict[int, ast.AST] = {}

    def generic_visit(self, node: ast.AST):
        for child in ast.iter_child_nodes(node):
            self.parent[id(child)] = node
        super().generic_visit(node)


class PythonParser:
    """Extracts functions and their statements from Python source code."""

    def extract_functions(self, source: str) -> list[FunctionInfo]:
        tree = ast.parse(source)
        source_lines = source.splitlines()

        # Build parent map in a single pass (fixes the O(n²) bug in the POC)
        mapper = _ParentMapper()
        mapper.visit(tree)

        functions: list[FunctionInfo] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            parent = mapper.parent.get(id(node))
            if isinstance(parent, ast.ClassDef):
                name = f"{parent.name}.{node.name}"
            else:
                name = node.name

            extractor = _StatementExtractor(source_lines)
            stmts = extractor.extract_from_body(node.body)
            if stmts:
                functions.append(FunctionInfo(name=name, statements=stmts))

        return functions
