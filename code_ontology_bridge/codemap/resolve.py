"""Resolve module names, imports and call sites against the whole repository.

Resolution is purely static and deliberately conservative: a callee is named
only when a plain dotted name leads to a definition through same-file
definitions, import bindings (following re-exports a few levels), or the
enclosing class and its statically resolvable base classes. Everything else is
kept as ``unresolved`` with a null callee.

A dotted name passed as an argument to a call is resolved by the same rules and
kept as a callback edge only when it names an internal function or method;
other argument names are ordinary data and produce no row.
"""

from __future__ import annotations

import builtins
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .analyzer import CallFact, FileFacts, ImportFact

MAX_REEXPORT_DEPTH = 3
MAX_BASE_DEPTH = 3
# A method with one of these decorators is read as a value, so passing it is not a callback.
PROPERTY_DECORATORS = frozenset({"property", "cached_property", "setter", "getter", "deleter"})


def is_test_path(file_id: str) -> bool:
    path = PurePosixPath(file_id)
    if any(part in ("tests", "test") for part in path.parts[:-1]):
        return True
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def module_name_for(file_id: str, package_dirs: set[str]) -> tuple[str, str]:
    """``(module, package)`` from the chain of ``__init__.py`` directories above the file."""
    path = PurePosixPath(file_id)
    parts: list[str] = []
    directory = path.parent
    while str(directory) not in ("", ".") and str(directory) in package_dirs:
        parts.insert(0, directory.name)
        directory = directory.parent
    if path.name == "__init__.py":
        module = ".".join(parts)
        package = module
    else:
        module = ".".join([*parts, path.stem])
        package = ".".join(parts)
    return module, package


@dataclass
class Binding:
    module: str
    attr: str | None  # None when the binding names a module


@dataclass
class FileContext:
    file_id: str
    module: str
    package: str
    is_package: bool
    facts: FileFacts
    symbols: dict[str, str] = field(default_factory=dict)  # qualname -> symbol_id
    definition_ids: dict[tuple[str, int], str] = field(default_factory=dict)
    bases: dict[str, list[str]] = field(default_factory=dict)  # class qualname -> base texts
    bindings: dict[str, Binding] = field(default_factory=dict)


@dataclass
class Resolution:
    callee_symbol_id: str | None
    resolution: str
    confidence: str


UNRESOLVED = Resolution(None, "unresolved", "low")
BUILTIN = Resolution(None, "builtin", "high")
EXTERNAL = Resolution(None, "external", "high")
DYNAMIC = Resolution(None, "dynamic_attribute", "low")
BUILTIN_NAMES = frozenset(dir(builtins))


class RepoIndex:
    def __init__(self, contexts: list[FileContext]):
        self.contexts = {c.file_id: c for c in contexts}
        by_module: dict[str, list[str]] = {}
        for ctx in contexts:
            if ctx.module:
                by_module.setdefault(ctx.module, []).append(ctx.file_id)
        # Only unambiguous module names resolve.
        self.module_to_file = {m: files[0] for m, files in by_module.items() if len(files) == 1}
        self.ambiguous_modules = sorted(m for m, files in by_module.items() if len(files) > 1)
        self.internal_roots = {m.split(".")[0] for m in by_module}
        self.symbol_kinds: dict[str, str] = {}
        self.properties: set[str] = set()
        for ctx in contexts:
            counts = Counter(sym.qualname for sym in ctx.facts.symbols)
            for sym in ctx.facts.symbols:
                symbol_id = f"{ctx.file_id}::{sym.qualname}"
                if counts[sym.qualname] > 1:
                    symbol_id += f"@L{sym.line_start}"
                else:
                    ctx.symbols[sym.qualname] = symbol_id
                ctx.definition_ids[(sym.qualname, sym.line_start)] = symbol_id
                self.symbol_kinds[symbol_id] = sym.kind
                if any(d.split(".")[-1] in PROPERTY_DECORATORS for d in sym.decorators):
                    self.properties.add(symbol_id)
                if sym.kind == "class":
                    ctx.bases[sym.qualname] = sym.bases
            for imp in ctx.facts.imports:
                binding = self._binding(ctx, imp)
                if binding is not None:
                    # Later bindings win, as at runtime for straight-line module code.
                    ctx.bindings[imp.bound_as] = binding

    # -- modules -------------------------------------------------------
    def absolute_module(self, ctx: FileContext, imp: ImportFact) -> str | None:
        if imp.level == 0:
            return imp.module
        base = ctx.module if ctx.is_package else ctx.package
        pieces = base.split(".") if base else []
        up = imp.level - 1
        if up > len(pieces):
            return None
        pieces = pieces[: len(pieces) - up] if up else pieces
        if imp.module:
            pieces = [*pieces, *imp.module.split(".")]
        return ".".join(pieces) or None

    def is_internal(self, module: str | None) -> bool:
        return bool(module) and module.split(".")[0] in self.internal_roots

    def _binding(self, ctx: FileContext, imp: ImportFact) -> Binding | None:
        module = self.absolute_module(ctx, imp)
        if module is None:
            return None
        if imp.name is None:
            if imp.bound_as == module.split(".")[0] and "." in module and imp.bound_as != module:
                return Binding(module.split(".")[0], None)
            return Binding(module, None)
        if imp.name == "*":
            return None
        sub = f"{module}.{imp.name}"
        if sub in self.module_to_file:
            return Binding(sub, None)
        return Binding(module, imp.name)

    def import_rows(self, ctx: FileContext) -> list[tuple[ImportFact, str, str | None, bool]]:
        """``(fact, module_name, imported_file_id, is_internal)`` per imported name."""
        rows = []
        for imp in ctx.facts.imports:
            module = self.absolute_module(ctx, imp)
            if module is None:
                rows.append((imp, "." * imp.level + (imp.module or ""), None, True))
                continue
            target = module
            if imp.name and imp.name != "*" and f"{module}.{imp.name}" in self.module_to_file:
                target = f"{module}.{imp.name}"
            rows.append((imp, target, self.module_to_file.get(target), self.is_internal(target)))
        return rows

    # -- symbols -------------------------------------------------------
    def _lookup_full(self, full: list[str], depth: int) -> str | None:
        """Longest module prefix of ``full`` that is a file, rest is a qualname in it."""
        for k in range(len(full) - 1, 0, -1):
            module = ".".join(full[:k])
            file_id = self.module_to_file.get(module)
            if file_id is None:
                continue
            found = self.lookup_symbol(file_id, full[k:], depth)
            if found:
                return found
            return None
        return None

    def lookup_symbol(self, file_id: str, qual: list[str], depth: int = 0) -> str | None:
        ctx = self.contexts[file_id]
        name = ".".join(qual)
        if name in ctx.symbols:
            return ctx.symbols[name]
        if depth >= MAX_REEXPORT_DEPTH:
            return None
        binding = ctx.bindings.get(qual[0])
        if binding is None:
            return None
        full = [*binding.module.split("."), *([binding.attr] if binding.attr else []), *qual[1:]]
        return self._lookup_full(full, depth + 1)

    def resolve_parts(self, ctx: FileContext, parts: list[str]) -> tuple[str | None, str]:
        """Resolve a dotted name used in ``ctx`` to ``(symbol_id, resolution)``."""
        head = parts[0]
        dotted = ".".join(parts)
        # Same-file: a top-level function or class, or Class.member on a top-level class.
        if head in ctx.symbols and dotted in ctx.symbols:
            return ctx.symbols[dotted], "same_file"
        binding = ctx.bindings.get(head)
        if binding is not None:
            full = [*binding.module.split("."), *([binding.attr] if binding.attr else []), *parts[1:]]
            found = self._lookup_full(full, 0)
            if found:
                return found, "imported"
        return None, "unresolved"

    def _method_in_class(self, class_symbol_id: str, method: str, depth: int) -> str | None:
        file_id, qual = class_symbol_id.split("::", 1)
        ctx = self.contexts[file_id]
        candidate = f"{qual}.{method}"
        if candidate in ctx.symbols:
            return ctx.symbols[candidate]
        if depth >= MAX_BASE_DEPTH:
            return None
        for base in ctx.bases.get(qual, []):
            base_id, _ = self.resolve_parts(ctx, base.split("."))
            if base_id:
                found = self._method_in_class(base_id, method, depth + 1)
                if found:
                    return found
        return None

    def _is_external_name(self, ctx: FileContext, name: str, depth: int = 0) -> bool:
        """True when ``name`` is bound to a non-internal import, or is a module-level
        name assigned from one (``logger = logging.getLogger(...)``)."""
        binding = ctx.bindings.get(name)
        if binding is not None:
            return not self.is_internal(binding.module)
        if name in ctx.symbols or depth >= 2:
            return False
        root = ctx.facts.module_assign_roots.get(name)
        return bool(root) and root != name and self._is_external_name(ctx, root, depth + 1)

    def resolve_call(self, ctx: FileContext, call: CallFact) -> Resolution:
        """Name an internal callee, or classify why there is none; never guess a target.

        Kinds after the internal ones: ``builtin`` (an unshadowed name from the
        builtins module), ``external`` (rooted in a non-internal import or a
        module-level name assigned from one), ``dynamic_attribute`` (an attribute
        call on an object whose type is not statically known), ``unresolved``.
        """
        parts = call.parts
        if not parts:
            return DYNAMIC if call.callee_text.startswith("<expr>.") else UNRESOLVED
        head = parts[0]
        if head in ("self", "cls") and call.enclosing_class:
            if len(parts) > 2:
                return DYNAMIC
            if len(parts) == 2:
                own = f"{call.enclosing_class}.{parts[1]}"
                if own in ctx.symbols:
                    return Resolution(ctx.symbols[own], "method_on_self", "high")
                class_id = ctx.symbols.get(call.enclosing_class)
                if class_id:
                    inherited = self._method_in_class(class_id, parts[1], 0)
                    if inherited:
                        return Resolution(inherited, "method_on_self", "low")
                return UNRESOLVED
        symbol_id, how = self.resolve_parts(ctx, parts)
        if symbol_id:
            return Resolution(symbol_id, how, "high")
        if self._is_external_name(ctx, head):
            return EXTERNAL
        if head in BUILTIN_NAMES and head not in ctx.symbols and head not in ctx.bindings and head not in ctx.facts.module_assign_roots:
            return BUILTIN
        if len(parts) > 1:
            return DYNAMIC
        return UNRESOLVED


    def resolve_callback(self, ctx: FileContext, call: CallFact) -> Resolution | None:
        """A function or method passed by reference, resolved like a call and
        recorded at low confidence; None when the name is not an internal
        function or method (data, a class, an external or unknown name)."""
        res = self.resolve_call(ctx, call)
        if res.callee_symbol_id is None or self.symbol_kinds.get(res.callee_symbol_id) not in ("function", "method"):
            return None
        if res.callee_symbol_id in self.properties:
            return None
        return Resolution(res.callee_symbol_id, res.resolution, "low")

    def resolve_base(self, ctx: FileContext, parts: list[str] | None) -> str | None:
        """Internal class a base-class expression names, or None."""
        if not parts:
            return None
        symbol_id, _ = self.resolve_parts(ctx, parts)
        if symbol_id and self.symbol_kinds.get(symbol_id) == "class":
            return symbol_id
        return None


def name_match_targets(test_file_id: str, non_test_files: list[str]) -> list[str]:
    """Non-test files whose stem is the test's stem without ``test_`` / ``_test``.

    When several files share the stem, the ones sharing the longest leading
    path with the test are kept.
    """
    path = PurePosixPath(test_file_id)
    stem = path.stem
    if stem.startswith("test_"):
        stem = stem[len("test_"):]
    elif stem.endswith("_test"):
        stem = stem[: -len("_test")]
    else:
        return []
    if not stem or stem == "__init__":
        return []
    candidates = [f for f in non_test_files if PurePosixPath(f).stem == stem]
    if len(candidates) <= 1:
        return candidates

    def shared(f: str) -> int:
        n = 0
        for a, b in zip(PurePosixPath(f).parts[:-1], path.parts[:-1]):
            if a != b:
                break
            n += 1
        return n

    best = max(shared(f) for f in candidates)
    return sorted(f for f in candidates if shared(f) == best)
