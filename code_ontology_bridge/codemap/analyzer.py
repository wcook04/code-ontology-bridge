"""Per-file static facts from the standard-library ``ast`` module.

One pass over a module records its docstring, the functions, methods and
classes it defines (with the base classes each class statement names), its
import statements, every call site together with the syntactic shape of the
callee, and every plain dotted name passed as an argument to a call (a
possible callback reference such as ``asyncio.to_thread(f, x)``). Resolution against the rest of the
repository happens later in ``resolve``; this module never looks outside the
file it parses.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class SymbolFact:
    qualname: str
    name: str
    kind: str  # function | method | class
    line_start: int
    line_end: int
    is_public: bool
    docstring: str | None
    bases: list[str] = field(default_factory=list)  # dotted base-class expressions (classes only)
    # Every positional base as written (``ast.unparse``) with the dotted name to resolve,
    # taken from ``Base`` or ``Base[T]``; None when the base is not a dotted name.
    base_exprs: list[tuple[str, list[str] | None]] = field(default_factory=list)
    # Dotted decorator names (``property``, ``functools.cached_property``, ``x.setter``).
    decorators: list[str] = field(default_factory=list)


@dataclass
class ImportFact:
    line: int
    level: int  # 0 for absolute
    module: str | None  # ``import a.b`` -> "a.b"; ``from .x import y`` -> "x"
    name: str | None  # imported attribute for ``from`` imports, None for ``import``
    bound_as: str  # local name the statement binds


@dataclass
class CallFact:
    caller: str  # qualname of the enclosing function, method or class
    enclosing_class: str | None  # qualname of the class whose method contains the call
    callee_text: str
    parts: list[str] | None  # dotted name parts when the callee is a plain dotted name
    line: int
    col: int
    # True for a dotted name passed as an argument (``to_thread(f)``, ``Thread(target=f)``)
    # rather than a call site; line and col are those of the argument.
    is_callback: bool = False


@dataclass
class FileFacts:
    docstring: str | None
    line_count: int
    symbols: list[SymbolFact]
    imports: list[ImportFact]
    calls: list[CallFact]
    module_level_calls: int
    # Module-level ``name = <dotted call or attribute>``: name -> root name of the value
    # (``logger = logging.getLogger(__name__)`` -> {"logger": "logging"}).
    module_assign_roots: dict[str, str] = field(default_factory=dict)


def dotted_parts(node: ast.AST) -> list[str] | None:
    """``a.b.c`` -> ["a", "b", "c"]; anything that is not a plain dotted name -> None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


# Receivers that inspect, compare or print a reference rather than invoke it.
NON_INVOKING_MODULES = frozenset({"inspect"})
NON_INVOKING_BUILTINS = frozenset(
    {"callable", "delattr", "dir", "getattr", "hasattr", "hash", "id", "isinstance", "issubclass", "print", "repr", "setattr", "str", "type", "vars"}
)


def _base_parts(node: ast.AST) -> list[str] | None:
    if isinstance(node, ast.Subscript):
        node = node.value
    return dotted_parts(node)


def bound_names(node: ast.AST) -> set[str]:
    """Names a function binds anywhere in its body, nested functions included:
    parameters, assignment and loop targets, ``as`` names, imports and nested
    definitions, minus names it declares ``global`` or ``nonlocal``."""
    names: set[str] = set()
    declared_outer: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.arg):
            names.add(n.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n is not node:
            names.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for alias in n.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            declared_outer.update(n.names)
    return names - declared_outer


def callee_text(node: ast.AST) -> str:
    parts = dotted_parts(node)
    if parts:
        return ".".join(parts)
    if isinstance(node, ast.Attribute):
        return f"<expr>.{node.attr}"
    return "<expr>"


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols: list[SymbolFact] = []
        self.imports: list[ImportFact] = []
        self.calls: list[CallFact] = []
        self.module_level_calls = 0
        self.module_assign_roots: dict[str, str] = {}
        # Stack of (qualname, kind) for enclosing definitions that are symbols.
        self._scope: list[tuple[str, str]] = []
        # Depth of nested functions inside a symbol: their calls belong to the symbol.
        self._public_stack: list[bool] = []
        # Names bound locally by each enclosing symbol (empty for class bodies).
        self._locals: list[set[str]] = []

    # -- scope helpers -------------------------------------------------
    def _caller(self) -> tuple[str | None, str | None]:
        if not self._scope:
            return None, None
        qual, kind = self._scope[-1]
        enclosing_class = None
        if kind == "method":
            enclosing_class = qual.rsplit(".", 1)[0]
        elif kind == "class":
            enclosing_class = None
        return qual, enclosing_class

    def _in_function(self) -> bool:
        return any(kind in ("function", "method") for _, kind in self._scope)

    # -- definitions ---------------------------------------------------
    def _visit_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, kind: str) -> None:
        if self._in_function():
            # Nested definitions are not symbols; their bodies count toward the enclosing symbol.
            self.generic_visit(node)
            return
        parent_qual = self._scope[-1][0] if self._scope else None
        qual = f"{parent_qual}.{node.name}" if parent_qual else node.name
        if kind != "class" and self._scope and self._scope[-1][1] == "class":
            kind = "method"
        public = not node.name.startswith("_") and all(self._public_stack)
        bases = []
        base_exprs: list[tuple[str, list[str] | None]] = []
        if isinstance(node, ast.ClassDef):
            bases = [".".join(p) for p in (dotted_parts(b) for b in node.bases) if p]
            base_exprs = [(ast.unparse(b), _base_parts(b)) for b in node.bases]
        self.symbols.append(
            SymbolFact(
                qualname=qual,
                name=node.name,
                kind=kind,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
                is_public=public,
                docstring=ast.get_docstring(node, clean=False),
                bases=bases,
                base_exprs=base_exprs,
                decorators=[".".join(p) for p in (dotted_parts(d) for d in node.decorator_list) if p],
            )
        )
        self._scope.append((qual, kind))
        self._public_stack.append(not node.name.startswith("_"))
        self._locals.append(set() if kind == "class" else bound_names(node))
        # Decorators, defaults and annotations are evaluated with the definition: attribute them to it.
        self.generic_visit(node)
        self._locals.pop()
        self._public_stack.pop()
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_def(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_def(node, "function")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_def(node, "class")

    # -- imports -------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self.imports.append(ImportFact(node.lineno, 0, alias.name, None, bound))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name
            self.imports.append(ImportFact(node.lineno, node.level or 0, node.module, alias.name, bound))

    # -- module-level assignments --------------------------------------
    def _record_assign(self, targets: list[ast.AST], value: ast.AST | None) -> None:
        if self._scope or value is None:
            return
        node = value.func if isinstance(value, ast.Call) else value
        parts = dotted_parts(node)
        if not parts:
            return
        for target in targets:
            if isinstance(target, ast.Name):
                self.module_assign_roots[target.id] = parts[0]

    def visit_Assign(self, node: ast.Assign) -> None:
        self._record_assign(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record_assign([node.target], node.value)
        self.generic_visit(node)

    # -- calls ---------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        caller, enclosing_class = self._caller()
        if caller is None:
            self.module_level_calls += 1
        else:
            self.calls.append(
                CallFact(
                    caller=caller,
                    enclosing_class=enclosing_class,
                    callee_text=callee_text(node.func),
                    parts=dotted_parts(node.func),
                    line=node.lineno,
                    col=node.col_offset,
                )
            )
            self._record_callback_references(node, caller, enclosing_class)
        self.generic_visit(node)

    def _record_callback_references(self, node: ast.Call, caller: str, enclosing_class: str | None) -> None:
        """Plain dotted names passed as positional or keyword arguments.

        A head name the enclosing function binds locally (a parameter, a local
        variable) is skipped, except ``self``/``cls`` inside a method; whether
        the name leads to an internal function is decided in ``resolve``.
        """
        receiver = dotted_parts(node.func)
        if receiver and (receiver[0] in NON_INVOKING_MODULES or (len(receiver) == 1 and receiver[0] in NON_INVOKING_BUILTINS)):
            return
        local = self._locals[-1] if self._locals else set()
        args = [a for a in node.args if not isinstance(a, ast.Starred)]
        args += [k.value for k in node.keywords if k.arg is not None]
        for arg in args:
            parts = dotted_parts(arg)
            if not parts:
                continue
            head = parts[0]
            if head in ("self", "cls") and enclosing_class:
                if len(parts) != 2:
                    continue
            elif head in local:
                continue
            self.calls.append(
                CallFact(
                    caller=caller,
                    enclosing_class=enclosing_class,
                    callee_text=".".join(parts),
                    parts=parts,
                    line=arg.lineno,
                    col=arg.col_offset,
                    is_callback=True,
                )
            )


def analyse_source(source: str, filename: str = "<unknown>") -> FileFacts:
    """Parse one module; raises ``SyntaxError`` (or ``ValueError`` for NUL bytes) when it cannot."""
    tree = ast.parse(source, filename=filename)
    visitor = _Visitor()
    visitor.visit(tree)
    return FileFacts(
        docstring=ast.get_docstring(tree, clean=False),
        line_count=len(source.splitlines()),
        symbols=visitor.symbols,
        imports=visitor.imports,
        calls=visitor.calls,
        module_level_calls=visitor.module_level_calls,
        module_assign_roots=visitor.module_assign_roots,
    )
