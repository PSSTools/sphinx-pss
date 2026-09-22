#****************************************************************************
#* domain.py
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
"""The ``pss`` Sphinx domain: object directives, roles, and the object index.

Autodoc emits these directives, and they are equally usable by hand — a project
can document a model it does not have sources for, or override what autodoc
produced, without leaving the domain.

Two details are worth knowing before changing anything here.

**The fullname is stashed during ``handle_signature``.** Sphinx calls
``_object_hierarchy_parts()`` *before* the signature's target ids exist, so
deriving the hierarchy from the node at that point yields nothing and the
object gets no entry in the sidebar TOC. Stashing the name while it is in hand
is the fix, and it is done from the start here rather than discovered later.

**Signatures produce real parameter nodes.** ``desc_parameterlist`` /
``desc_parameter`` rather than a formatted string, so that a function's
arguments and an action's flow signature are structured data in the doctree —
which is what lets type names inside them become links.
"""

from __future__ import annotations

from typing import Any, Iterable

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.directives import ObjectDescription
from sphinx.domains import Domain, ObjType
from sphinx.roles import XRefRole
from sphinx.util import logging
from sphinx.util.nodes import make_refnode

logger = logging.getLogger(__name__)


#: ``PssObject.kind`` -> the label shown in the object index and before a
#: signature. Ordered as the domain registers them.
KIND_LABELS = {
    "package": "package",
    "component": "component",
    "action": "action",
    "monitor": "monitor",
    "struct": "struct",
    "buffer": "buffer",
    "stream": "stream",
    "state": "state",
    "resource": "resource",
    "enum": "enum",
    "enum_item": "enum value",
    "field": "field",
    "flow_ref": "flow reference",
    "resource_claim": "resource claim",
    "constraint": "constraint",
    "function": "function",
    "pool": "pool",
}

#: Kinds whose label is *not* a PSS keyword, and so must not be printed in a
#: signature. A field is written ``rand int size``, not ``rand field size``;
#: a flow reference leads with its direction, which is already a qualifier.
#: Printing the label for these makes the signature stop being a quotation of
#: the source, which is the one thing a signature has to be.
UNKEYWORDED_KINDS = frozenset({"field", "flow_ref", "resource_claim", "enum_item"})

#: Kinds that own members, and so open a nesting level for the objects
#: declared inside them.
NESTING_KINDS = frozenset(
    {
        "package",
        "component",
        "action",
        "monitor",
        "struct",
        "buffer",
        "stream",
        "state",
        "resource",
        "enum",
    }
)

#: Role name -> the kinds it may resolve to. ``obj`` matches anything, which
#: is what makes it the role to reach for when the kind is not worth spelling.
ROLE_KINDS = {
    "pkg": ("package",),
    "comp": ("component",),
    "action": ("action",),
    "monitor": ("monitor",),
    "struct": ("struct",),
    "buffer": ("buffer",),
    "stream": ("stream",),
    "state": ("state",),
    "resource": ("resource",),
    "enum": ("enum",),
    "func": ("function",),
    "field": ("field", "flow_ref", "resource_claim", "enum_item"),
    "constraint": ("constraint",),
    "type": tuple(NESTING_KINDS),
    "obj": (),
}

#: How many candidates an ambiguity warning lists before it stops.
MAX_REPORTED_CANDIDATES = 5

#: Marks a reference the extension generated itself rather than one an author
#: wrote — currently the type names inside a signature. These must not warn:
#: a field declared ``int len`` emits a reference to ``int``, which has no
#: page and never will, and warning once per field would bury the references
#: that are genuinely broken.
#:
#: A dedicated attribute rather than Sphinx's ``refwarn``, which ``XRefRole``
#: sets to ``False`` on every role node it creates — reusing it silences the
#: author-written references this warning exists to catch.
GENERATED_REF = "pss:generated"


def qualname_parts(qualname: str) -> tuple[str, ...]:
    return tuple(p for p in qualname.split("::") if p)


class PssObjectDescription(ObjectDescription[str]):
    """Base for every ``pss:<kind>`` directive."""

    #: Set by `make_directive` for each registered kind.
    kind = "obj"

    option_spec = {
        **ObjectDescription.option_spec,
        "no-index-entry": directives.flag,
        "module": directives.unchanged,
        "qualname": directives.unchanged,
        "type": directives.unchanged,
        "qualifiers": directives.unchanged,
        "extends": directives.unchanged,
        # Flow options, accepted on any object so a hand-written action can
        # carry the same signature autodoc produces.
        "input": directives.unchanged,
        "output": directives.unchanged,
        "lock": directives.unchanged,
        "share": directives.unchanged,
    }

    def handle_signature(self, sig: str, signode: addnodes.desc_signature) -> str:
        """Render one signature and return the name that identifies it."""
        parsed = parse_signature(sig)

        # ``:qualname:`` sets the *target*, not what is displayed. Autodoc
        # passes it so a member's id is stable no matter which directive
        # rendered it, but the signature must still read as the declaration
        # does — ``rand int len``, not ``rand int dma_pkg::Dma::Xfer::len``.
        name = self.options.get("qualname") or parsed.name

        # Everything below renders in PSS declaration order --
        # ``[qualifiers] [keyword] [type] name [(params)] [: base]`` -- so the
        # signature reads as a quotation of the source rather than a
        # rearrangement of it.
        # A model-rendered signature already leads with the PSS keyword
        # (``action Xfer``), and `parse_signature` collects it as a qualifier.
        # Dropping it here means the keyword is printed exactly once whether
        # the signature came from autodoc or was hand-written without it.
        keyword = KIND_LABELS.get(self.kind, self.kind)
        written_qualifiers = [q for q in parsed.qualifiers if q != keyword]

        qualifiers = self.options.get("qualifiers") or " ".join(written_qualifiers)
        if qualifiers:
            signode += addnodes.desc_annotation(
                qualifiers + " ", "", nodes.Text(qualifiers + " ")
            )

        if self.kind not in UNKEYWORDED_KINDS:
            signode += addnodes.desc_annotation(
                keyword + " ", "", nodes.Text(keyword + " ")
            )

        type_name = self.options.get("type") or parsed.type_name
        if type_name:
            signode += self._type_reference(type_name)
            signode += nodes.Text(" ")

        prefix = self._name_prefix(parsed.name)
        if prefix:
            signode += addnodes.desc_addname(prefix, prefix)
        signode += addnodes.desc_name(parsed.name, parsed.name)

        if parsed.parameters is not None:
            signode += self._parameter_list(parsed.parameters)

        extends = self.options.get("extends") or parsed.extends
        if extends:
            signode += addnodes.desc_annotation(" : ", "", nodes.Text(" : "))
            signode += self._type_reference(extends)

        # Stash the fully qualified name now. Sphinx calls
        # _object_hierarchy_parts() before the target ids exist, so reading it
        # back off the node there would find nothing and the object would get
        # no TOC entry.
        signode["pss:fullname"] = self._fullname(name)
        signode["pss:kind"] = self.kind

        return signode["pss:fullname"]

    # --- naming ------------------------------------------------------------

    def _current_scope(self) -> str:
        stack: list[str] = self.env.ref_context.get("pss:scope-stack", [])
        return stack[-1] if stack else ""

    def _fullname(self, name: str) -> str:
        if "::" in name:
            return name
        scope = self.options.get("module") or self._current_scope()
        return f"{scope}::{name}" if scope else name

    def _name_prefix(self, name: str) -> str:
        """The qualified prefix shown before the name, if any.

        Only shown when the signature itself was written qualified — repeating
        the enclosing scope on every nested member is noise.
        """
        return name.rsplit("::", 1)[0] + "::" if "::" in name else ""

    # --- signature pieces --------------------------------------------------

    def _parameter_list(self, parameters: Iterable[str]) -> addnodes.desc_parameterlist:
        """Real ``desc_parameter`` nodes, not a formatted string."""
        paramlist = addnodes.desc_parameterlist()
        for parameter in parameters:
            node = addnodes.desc_parameter("", "", noemph=True)
            declared_type, _, parameter_name = parameter.rpartition(" ")
            if declared_type:
                node += self._type_reference(declared_type)
                node += nodes.Text(" ")
            node += nodes.Text(parameter_name)
            paramlist += node
        return paramlist

    def _type_reference(self, type_name: str) -> nodes.Node:
        """A type name in a signature, as a pending cross reference.

        Emitted unconditionally: whether it resolves is decided later, against
        the finished index, and an unresolved reference degrades to plain text
        rather than failing. A built-in like ``int`` simply never resolves.
        """
        node = addnodes.pending_xref(
            "",
            nodes.Text(type_name),
            refdomain="pss",
            reftype="type",
            reftarget=type_name,
            refspecific=True,
            **{"pss:scope": self._current_scope(), GENERATED_REF: True},
        )
        node["refwarn"] = False
        return node

    # --- registration ------------------------------------------------------

    def add_target_and_index(
        self, name: str, sig: str, signode: addnodes.desc_signature
    ) -> None:
        node_id = make_node_id(name)
        signode["ids"].append(node_id)
        self.state.document.note_explicit_target(signode)

        domain = self.env.domains["pss"]
        domain.note_object(name, self.kind, node_id, location=signode)

        if "no-index-entry" not in self.options:
            label = KIND_LABELS.get(self.kind, self.kind)
            display = name.rsplit("::", 1)[-1]
            self.indexnode["entries"].append(
                ("single", f"{display} ({label} in PSS)", node_id, "", None)
            )

    def _object_hierarchy_parts(
        self, sig_node: addnodes.desc_signature
    ) -> tuple[str, ...]:
        """Split the stashed fullname for the sidebar TOC."""
        return qualname_parts(sig_node.get("pss:fullname", ""))

    def _toc_entry_name(self, sig_node: addnodes.desc_signature) -> str:
        if not sig_node.get("_toc_parts"):
            return ""
        return sig_node["_toc_parts"][-1]

    # --- nesting -----------------------------------------------------------

    def before_content(self) -> None:
        """Open a scope so members inside the body get qualified names."""
        if self.kind not in NESTING_KINDS or not self.names:
            self._pushed_scope = False
            return
        stack = self.env.ref_context.setdefault("pss:scope-stack", [])
        stack.append(self.names[-1])
        self._pushed_scope = True

    def after_content(self) -> None:
        if getattr(self, "_pushed_scope", False):
            self.env.ref_context["pss:scope-stack"].pop()
            self._pushed_scope = False


class ParsedSignature:
    """The pieces `parse_signature` recovers from a signature string."""

    __slots__ = ("name", "qualifiers", "parameters", "type_name", "extends")

    def __init__(
        self,
        name: str,
        qualifiers: list[str],
        parameters: list[str] | None,
        type_name: str | None,
        extends: str | None,
    ) -> None:
        self.name = name
        self.qualifiers = qualifiers
        self.parameters = parameters
        self.type_name = type_name
        self.extends = extends


#: Keywords that can lead a signature and are the kind, not the name.
LEADING_KEYWORDS = frozenset(KIND_LABELS) | {
    "input",
    "output",
    "lock",
    "share",
    "pool",
    "abstract",
    "rand",
    "static",
    "const",
    "pure",
    "target",
    "solve",
    "private",
    "protected",
    "instance",
}


def parse_signature(sig: str) -> ParsedSignature:
    """Recover a name and its decorations from a signature string.

    Deliberately forgiving. An unparseable signature degrades to "the whole
    string is the name" rather than failing the build: a documentation tool
    that refuses to render an unusual declaration is worse than one that
    renders it plainly.
    """
    text = sig.strip()
    extends = None
    if " : " in text:
        text, _, extends = text.partition(" : ")
        text, extends = text.strip(), extends.strip()

    parameters: list[str] | None = None
    if text.endswith(")") and "(" in text:
        head, _, tail = text.partition("(")
        text = head.strip()
        inner = tail[:-1].strip()
        parameters = [p.strip() for p in inner.split(",") if p.strip()] if inner else []

    words = text.split()
    if not words:
        return ParsedSignature(sig.strip(), [], parameters, None, extends)

    name = words[-1]
    leading = words[:-1]

    qualifiers = [w for w in leading if w in LEADING_KEYWORDS]
    type_words = [w for w in leading if w not in LEADING_KEYWORDS]
    type_name = " ".join(type_words) if type_words else None

    return ParsedSignature(name, qualifiers, parameters, type_name, extends)


#: Characters kept verbatim in a node id. Everything else becomes ``-``.
_ID_SAFE = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_."
)


def make_node_id(qualname: str) -> str:
    """A stable HTML id for ``qualname``.

    ``::`` is not usable in a fragment identifier, so it becomes ``.`` — which
    reads well in a URL and matches what the Python domain produces for a
    dotted name.

    Case is **preserved**, unlike ``docutils.nodes.make_id``, which lowercases.
    PSS convention is ``PascalCase`` types alongside ``snake_case`` members, so
    lowercasing collides ``DmaBuf`` with a hypothetical ``dmabuf`` and, worse,
    makes the collision depend on what else the project happens to declare.
    """
    dotted = qualname.replace("::", ".")
    return "pss-" + "".join(c if c in _ID_SAFE else "-" for c in dotted)


class PssXRefRole(XRefRole):
    """A ``:pss:…:`` cross-reference role."""

    def process_link(self, env, refnode, has_explicit_title, title, target):
        refnode["pss:scope"] = env.ref_context.get("pss:scope-stack", [""])[-1] if env.ref_context.get("pss:scope-stack") else ""
        if not has_explicit_title:
            # A qualified target reads better as its last component, the way
            # the Python domain shortens ``a.b.c`` with a leading ``~``.
            if title.startswith("~"):
                title = title[1:].rsplit("::", 1)[-1]
                target = target.lstrip("~")
        return title, target


class PssDomain(Domain):
    """The ``pss`` domain."""

    name = "pss"
    label = "PSS"

    object_types = {
        kind: ObjType(label, kind, "obj")
        for kind, label in KIND_LABELS.items()
    }

    directives: dict[str, Any] = {}
    roles: dict[str, Any] = {
        role: PssXRefRole() for role in ROLE_KINDS
    }

    initial_data: dict[str, Any] = {
        # qualname -> (docname, node_id, kind)
        "objects": {},
    }

    @property
    def objects(self) -> dict[str, tuple[str, str, str]]:
        return self.data.setdefault("objects", {})

    def note_object(
        self, qualname: str, kind: str, node_id: str, location: Any = None
    ) -> None:
        if qualname in self.objects:
            other_doc = self.objects[qualname][0]
            logger.warning(
                "duplicate PSS object description of %s; other instance in %s",
                qualname,
                other_doc,
                location=location,
                type="pss",
                subtype="duplicate_object",
            )
        self.objects[qualname] = (self.env.docname, node_id, kind)

    # --- domain plumbing ---------------------------------------------------

    def clear_doc(self, docname: str) -> None:
        for qualname, (doc, _, _) in list(self.objects.items()):
            if doc == docname:
                del self.objects[qualname]

    def merge_domaindata(self, docnames: list[str], otherdata: dict) -> None:
        for qualname, entry in otherdata.get("objects", {}).items():
            if entry[0] in docnames:
                self.objects[qualname] = entry

    def get_objects(self):
        """Feeds the search index and ``objects.inv``."""
        for qualname, (docname, node_id, kind) in self.objects.items():
            yield (qualname, qualname, kind, docname, node_id, 1)

    # --- resolution --------------------------------------------------------

    def find_object(
        self, target: str, kinds: tuple[str, ...] = (), scope: str = ""
    ) -> tuple[str, tuple[str, str, str]] | None:
        """Resolve ``target`` as seen from ``scope``.

        Matches the lexical resolution the model uses: enclosing scopes
        innermost-first, then the target as already qualified, then a unique
        suffix match. The suffix step is what makes ``:pss:action:`Xfer``` work
        from anywhere, and it is skipped when ambiguous so the caller can
        report candidates instead of picking one.
        """

        def acceptable(entry: tuple[str, str, str]) -> bool:
            return not kinds or entry[2] in kinds

        parts = qualname_parts(scope)
        for i in range(len(parts), 0, -1):
            candidate = "::".join(parts[:i]) + "::" + target
            entry = self.objects.get(candidate)
            if entry is not None and acceptable(entry):
                return candidate, entry

        entry = self.objects.get(target)
        if entry is not None and acceptable(entry):
            return target, entry

        matches = [
            (qualname, entry)
            for qualname, entry in self.objects.items()
            if acceptable(entry)
            and (qualname == target or qualname.endswith("::" + target))
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def candidates_for(self, target: str, kinds: tuple[str, ...] = ()) -> list[str]:
        """Every qualified name ``target`` could have meant."""
        return sorted(
            qualname
            for qualname, entry in self.objects.items()
            if (not kinds or entry[2] in kinds)
            and (qualname == target or qualname.endswith("::" + target))
        )

    def resolve_xref(
        self, env, fromdocname, builder, typ, target, node, contnode
    ):
        kinds = ROLE_KINDS.get(typ, ())
        scope = node.get("pss:scope", "")
        found = self.find_object(target, kinds, scope)

        if found is None:
            self._warn_unresolved(typ, target, kinds, node)
            return None

        qualname, (docname, node_id, _) = found
        return make_refnode(builder, fromdocname, docname, node_id, contnode, qualname)

    def resolve_any_xref(
        self, env, fromdocname, builder, target, node, contnode
    ):
        found = self.find_object(target, (), node.get("pss:scope", ""))
        if found is None:
            return []
        qualname, (docname, node_id, kind) = found
        return [
            (
                f"pss:{kind}",
                make_refnode(
                    builder, fromdocname, docname, node_id, contnode, qualname
                ),
            )
        ]

    def _warn_unresolved(self, typ: str, target: str, kinds, node) -> None:
        """Report an unresolved reference, with candidates when there are any.

        A bare "target not found" for an ambiguous name is the least useful
        warning a documentation tool can emit, since the name plainly does
        exist. Listing what it could have meant turns it into an instruction.
        """
        if node.get(GENERATED_REF):
            return

        candidates = self.candidates_for(target, kinds)
        if candidates:
            shown = ", ".join(candidates[:MAX_REPORTED_CANDIDATES])
            if len(candidates) > MAX_REPORTED_CANDIDATES:
                shown += f", … ({len(candidates)} total)"
            message = (
                f"ambiguous PSS reference :pss:{typ}:`{target}`; "
                f"qualify it as one of: {shown}"
            )
        else:
            message = f"unknown PSS object :pss:{typ}:`{target}`"

        logger.warning(
            message, location=node, type="pss", subtype="ref"
        )


def make_directive(kind: str) -> type[PssObjectDescription]:
    """Build the ``pss:<kind>`` directive class."""
    return type(
        f"Pss{kind.title().replace('_', '')}Directive",
        (PssObjectDescription,),
        {"kind": kind, "__doc__": f"Describes a PSS {KIND_LABELS[kind]}."},
    )


PssDomain.directives = {kind: make_directive(kind) for kind in KIND_LABELS}


def setup(app) -> None:
    app.add_domain(PssDomain)
