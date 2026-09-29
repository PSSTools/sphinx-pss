#****************************************************************************
#* calls.py
#*
#* Copyright 2026 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#****************************************************************************
"""Which function a call calls (programming-steps plan section 1.2).

A call's own ``getTarget()`` resolves only the first element of its path, so
``comp.sub.sub_fn()`` resolves to the ``comp`` field. ``refs.occurrences()``
binds every identifier, member calls included, so a call is followed through
the occurrence of its *last* path element:

1. every occurrence in the model, sorted by position, once per build;
2. the occurrences inside a statement's text (its start to its ``;``, from
   `sphinx_pss.model.source_text`) whose declaration is a function;
3. that declaration, a ``FunctionPrototype`` with no parent, mapped to its
   ``SymbolFunctionScope`` through a map built by walking the linked tree.

A standard-library call resolves to a template prototype that isn't in the
map, and comes back with no callee: library functions have no steps.

Both indexes are built on first use and cached on the `ParsedModel`.
"""

from __future__ import annotations

import bisect
import dataclasses
from typing import Any

from .locations import node_type_name
from .parse import ParsedModel, iter_children
from .source_text import SourceText

__all__ = ["Call", "Callee", "CallIndex", "SymbolIndex", "call_index", "source_text", "symbol_index"]

_FUNCTION_SCOPE = "SymbolFunctionScope"
#: Linked-tree nodes that can contain functions or types.
_CONTAINERS = frozenset({"SymbolScope", "SymbolTypeScope"})


@dataclasses.dataclass(frozen=True)
class Callee:
    """A user function a call resolved to."""

    qualname: str
    #: The linked ``SymbolFunctionScope``.
    scope: Any = dataclasses.field(compare=False, repr=False)

    def body(self) -> Any | None:
        """The function's body, or ``None`` when it is only declared."""
        return function_body(self.scope)


@dataclasses.dataclass(frozen=True)
class Call:
    """One call, at the position of the called name."""

    #: The called name as written: the last element of ``comp.sub.fn``.
    name: str
    fileid: int
    line: int
    col: int
    #: ``None`` for a library function, or one that didn't resolve.
    callee: Callee | None


def function_body(scope: Any) -> Any | None:
    """The body of a linked function, or ``None`` when it has no definition."""
    definition = getattr(scope, "getDefinition", lambda: None)() or getattr(
        scope, "getTarget", lambda: None
    )()
    return definition.getBody() if definition is not None else None


class SymbolIndex:
    """Functions and types of the linked model, by qualified name and prototype.

    Qualified names are built the way `sphinx_pss.model.builder` builds them,
    by the same walk, so a name from the object index finds its scope here.
    """

    def __init__(self, root: Any) -> None:
        self.scopes: dict[str, Any] = {}
        self._by_proto: dict[Any, Callee] = {}
        if root is not None:
            self._walk(root, "")

    def _walk(self, node: Any, prefix: str) -> None:
        for child in iter_children(node):
            kind = node_type_name(child)
            if kind != _FUNCTION_SCOPE and kind not in _CONTAINERS:
                continue
            name = _name(child)
            if not name or name.startswith("<"):
                continue
            qualname = f"{prefix}::{name}" if prefix else name
            self.scopes.setdefault(qualname, child)
            if kind == _FUNCTION_SCOPE:
                callee = Callee(qualname, child)
                for i in range(child.numPrototypes()):
                    self._by_proto[child.getPrototype(i)] = callee
            else:
                self._walk(child, qualname)

    def callee(self, prototype: Any) -> Callee | None:
        try:
            return self._by_proto.get(prototype)
        except TypeError:  # pragma: no cover - an unhashable declaration
            return None


class CallIndex:
    """The calls inside any statement, resolved."""

    def __init__(self, model: ParsedModel) -> None:
        from pssparser import refs

        self._symbols = symbol_index(model)
        self._text = source_text(model)
        self._by_file: dict[int, list[tuple[int, int, Any]]] = {}
        if model.root is not None:
            for occ in refs.occurrences(model.root):
                if occ.is_declaration or not _is_function(occ.decl):
                    continue
                self._by_file.setdefault(occ.fileid, []).append((occ.line, occ.col, occ))
        for entries in self._by_file.values():
            entries.sort(key=lambda e: (e[0], e[1]))

    def calls_in(self, stmt: Any) -> list[Call]:
        """The calls a simple statement makes, in source order.

        The statement's extent is its start to the ``;`` that ends it; a
        statement whose end isn't found makes no calls, rather than borrowing
        the next statement's.
        """
        loc = stmt.getLocation()
        end = self._text.statement_end(loc)
        entries = self._by_file.get(loc.fileid)
        if end is None or not entries:
            return []
        lo = bisect.bisect_left(entries, (loc.lineno, loc.linepos), key=lambda e: (e[0], e[1]))
        hi = bisect.bisect_right(entries, end, key=lambda e: (e[0], e[1]))
        return [
            Call(name=occ.text, fileid=loc.fileid, line=line, col=col, callee=self._symbols.callee(occ.decl))
            for line, col, occ in entries[lo:hi]
        ]


def _is_function(decl: Any) -> bool:
    kind = node_type_name(decl)
    return kind.startswith("Function") and kind != "FunctionParamDecl"


def _name(node: Any) -> str | None:
    from .builder import _name_of

    return _name_of(node)


def symbol_index(model: ParsedModel) -> SymbolIndex:
    return model.cached("calls.symbols", lambda: SymbolIndex(model.root))


def call_index(model: ParsedModel) -> CallIndex:
    return model.cached("calls.calls", lambda: CallIndex(model))


def source_text(model: ParsedModel) -> SourceText:
    return model.cached("source_text", lambda: SourceText(model.file_map))
