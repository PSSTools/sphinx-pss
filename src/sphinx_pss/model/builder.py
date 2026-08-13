"""Walks the linked symbol tree and emits `PssObject`\\ s.

This is the only module that knows ``pssparser``'s node shapes. It walks the
*linked* tree rather than the per-file ASTs, because that is where ``extend``
merging, inheritance and type resolution have happened — the linked tree is the
documentation view (design section 4.1).

Three parser behaviors drive the shape of the code here, all recorded in the
implementation plan:

* a linked type wrapper hides its declaration's docstring, so nodes are
  unwrapped before being read (``SymbolTypeScope.getTarget()``);
* packages and enums expose no declaration at all, so their doc comment is
  recovered through `ParsedModel.declaration_at` (finding ``U-1``);
* a merged ``extend`` member keeps its own extend-site location, which is
  exactly what makes provenance derivable without any parser change.
"""

from __future__ import annotations

from typing import Any, Iterable

from .locations import (
    STDLIB_FILEID,
    is_synthesized,
    node_source_ref,
    node_type_name,
)
from .objects import (
    PROVENANCE_DECLARATION,
    PROVENANCE_EXTENSION,
    Annotation,
    FlowRef,
    FlowSpec,
    Provenance,
    PssObject,
    ResourceClaim,
    SourceRef,
    TemplateParam,
)
from .parse import ParsedModel, iter_children, unwrap

# --- parser enumerations ----------------------------------------------------
#
# Mirrored as plain data rather than imported, so that a value added upstream
# shows up as an unmapped kind rather than an ImportError.

#: ``ast.StructKind`` -> ``PssObject.kind``. A PSS "struct" declaration covers
#: all four flow-object kinds plus the plain struct, distinguished only by this
#: enumeration.
STRUCT_KIND_TO_KIND = {
    0: "buffer",
    1: "struct",
    2: "resource",
    3: "stream",
    4: "state",
}

#: ``ast.FieldAttr`` bit values -> the qualifier keyword as written in source.
FIELD_ATTR_QUALIFIERS = (
    (1, "action"),
    (4, "rand"),
    (8, "const"),
    (16, "static"),
    (32, "instance"),
    (64, "private"),
    (128, "protected"),
)

#: Bit set on fields the compiler injected. Such a field is filtered even when
#: it happens to carry a location.
FIELD_ATTR_BUILTIN = 2

#: Qualifier order as PSS writes it: ``static const int x``, never
#: ``const static``.
QUALIFIER_ORDER = (
    "action",
    "private",
    "protected",
    "static",
    "const",
    "instance",
    "rand",
)


def _name_of(node: Any) -> str | None:
    """The declared name of ``node``, whatever shape the accessor returns.

    Some nodes return a plain string, others an ``ExprId``. Normalizing here
    keeps every caller from having to know which is which.
    """
    getter = getattr(node, "getName", None)
    if getter is None:
        return None
    try:
        name = getter()
    except TypeError:  # pragma: no cover - indexed getName overloads
        return None
    if name is None:
        return None
    if hasattr(name, "getId"):
        try:
            return str(name.getId())
        except TypeError:  # pragma: no cover
            return None
    return str(name)


def _docstring_of(node: Any) -> str | None:
    getter = getattr(node, "getDocstring", None)
    if getter is None:
        return None
    doc = getter()
    return doc or None


def _annotations_of(node: Any) -> list[Annotation]:
    """Capture applied annotations as metadata.

    Rendered as a field list on the element; deliberately *not* a documentation
    source (design section 3.2).
    """
    getter = getattr(node, "getAnnotations", None)
    if getter is None:
        return []
    try:
        raw = getter()
    except TypeError:  # pragma: no cover
        return []
    if raw is None:
        return []

    result: list[Annotation] = []
    for i in range(len(raw)):
        try:
            annotation = node.getAnnotation(i)
        except Exception:  # noqa: BLE001 - pragma: no cover
            continue
        name = _type_identifier_name(getattr(annotation, "getType", lambda: None)())
        params: dict[str, str] = {}
        get_params = getattr(annotation, "getParameters", None)
        if get_params is not None:
            plist = get_params()
            for j in range(len(plist)):
                param = annotation.getParameter(j)
                pname = _name_of(param) or str(j)
                params[pname] = _expr_text(getattr(param, "getValue", lambda: None)())
        result.append(Annotation(name=name or "?", params=params))
    return result


def _expr_text(expr: Any) -> str:
    """A best-effort source-like rendering of an expression node.

    Expression printing is not part of Phase 1 — constraint bodies are rendered
    from source in Phase 4 — so this covers the literal forms that appear in
    annotation parameters and field initializers and no more.
    """
    if expr is None:
        return ""
    for accessor in ("getValue", "getId", "getImage"):
        getter = getattr(expr, accessor, None)
        if getter is None:
            continue
        try:
            value = getter()
        except TypeError:  # pragma: no cover
            continue
        if value is not None and not hasattr(value, "getLocation"):
            return str(value)
    return ""


def _type_identifier_name(type_id: Any) -> str | None:
    """Render a ``TypeIdentifier`` as its written ``a::b::c`` name.

    The resolved target is unreachable from Python — ``getTarget()`` returns a
    ``SymbolRefPath`` that exposes only an index (finding ``U-3``) — so the
    written name is what we have. `sphinx_pss.model.index` resolves it to a
    qualified name against the index, which is the design's model anyway.
    """
    if type_id is None:
        return None
    get_elems = getattr(type_id, "getElems", None)
    if get_elems is None:
        return None
    elems = get_elems()
    parts: list[str] = []
    for i in range(len(elems)):
        elem = type_id.getElem(i)
        ident = getattr(elem, "getId", lambda: None)()
        if ident is None:
            continue
        parts.append(str(ident.getId() if hasattr(ident, "getId") else ident))
    return "::".join(parts) if parts else None


#: Width the parser fills in when an integer type is written without one.
#: ``int`` is 32-bit signed, ``bit`` is 1-bit unsigned (PSS 3.1 section 8.2).
DEFAULT_INT_WIDTH = {True: 32, False: 1}


def _int_type_name(data_type: Any) -> str:
    """Render ``DataTypeInt`` the way it was written.

    The parser always populates a width, substituting the default when the
    source gave none, so an explicit width is detected by comparing against
    that default. Rendering the default back out would turn every plain ``int``
    into ``int [31:0]``, which is correct PSS but not what the author wrote.
    """
    signed = bool(getattr(data_type, "getIs_signed", lambda: True)())
    base = "int" if signed else "bit"

    width_expr = getattr(data_type, "getWidth", lambda: None)()
    width = getattr(width_expr, "getValue", lambda: None)() if width_expr else None
    if width is None or int(width) == DEFAULT_INT_WIDTH[signed]:
        return base
    return f"{base} [{int(width) - 1}:0]"


def _type_name(data_type: Any) -> str | None:
    """Render a declared type as it was written."""
    if data_type is None:
        return None

    kind = node_type_name(data_type)
    if kind == "DataTypeUserDefined":
        return _type_identifier_name(data_type.getType_id())
    if kind == "DataTypeInt":
        return _int_type_name(data_type)
    if kind == "DataTypeBool":
        return "bool"
    if kind == "DataTypeString":
        return "string"
    if kind == "DataTypeChandle":
        return "chandle"
    if kind == "DataTypeEnum":
        return _type_identifier_name(getattr(data_type, "getTid", lambda: None)())
    if kind == "DataTypeRef":
        inner = _type_name(getattr(data_type, "getType", lambda: None)())
        return f"ref {inner}" if inner else "ref"
    return None


def _qualifiers_of_field(field: Any) -> list[str]:
    """Decode a ``Field``'s attribute bitmask into source keywords."""
    attr = getattr(field, "getAttr", lambda: 0)()
    try:
        bits = int(attr)
    except (TypeError, ValueError):  # pragma: no cover
        bits = int(getattr(attr, "value", 0))

    present = {name for bit, name in FIELD_ATTR_QUALIFIERS if bits & bit}
    return [q for q in QUALIFIER_ORDER if q in present]


def _is_builtin_field(field: Any) -> bool:
    attr = getattr(field, "getAttr", lambda: 0)()
    try:
        return bool(int(attr) & FIELD_ATTR_BUILTIN)
    except (TypeError, ValueError):  # pragma: no cover
        return False


def _template_params_of(node: Any) -> list[TemplateParam]:
    getter = getattr(node, "getParams", None)
    if getter is None:
        return []
    try:
        params = getter()
    except TypeError:  # pragma: no cover
        return []
    if params is None:
        return []

    result: list[TemplateParam] = []
    get_param = getattr(params, "getParam", None)
    entries = getattr(params, "getParams", lambda: None)()
    if entries is None or get_param is None:
        return result
    for i in range(len(entries)):
        param = get_param(i)
        name = _name_of(param)
        if name:
            result.append(TemplateParam(name=name))
    return result


class ModelBuilder:
    """Builds the `PssObject` tree for one parsed model.

    Instantiated once per build by `sphinx_pss.model.index.PssIndex`; the
    traversal is stateless apart from the model it reads.
    """

    def __init__(self, model: ParsedModel, *, document_stdlib: bool = False) -> None:
        self._model = model
        self._document_stdlib = document_stdlib

    # --- entry point -------------------------------------------------------

    def build(self) -> list[PssObject]:
        """Top-level objects, in the order the parser reports them.

        For a linked model these are the packages the linker produced, with
        ``extend`` merged in. For a degraded model (``pss_tolerate_link_errors``
        after a link failure) they are the declarations of each file in turn:
        the same member builders run, but nothing is merged or resolved.
        """
        roots = (
            [self._model.root]
            if self._model.linked and self._model.root is not None
            else self._model.user_units()
        )

        objects: list[PssObject] = []
        for root in roots:
            for child in iter_children(root):
                obj = self._build_node(child, parent_qualname="")
                if obj is not None:
                    objects.append(obj)
        return objects

    # --- helpers -----------------------------------------------------------

    def _source_ref(self, node: Any) -> SourceRef | None:
        return node_source_ref(node, self._model.file_map)

    def _fileid_of(self, node: Any) -> int:
        getter = getattr(node, "getLocation", None)
        if getter is None:
            return -1
        loc = getter()
        return loc.fileid if loc is not None else -1

    def _doc_for(self, node: Any, declaration: Any) -> str | None:
        """The element's doc comment, from wherever the parser exposes it."""
        doc = _docstring_of(declaration)
        if doc is None and declaration is not node:
            doc = _docstring_of(node)
        if doc is None:
            # Packages and enums: unreachable from the linked tree, recovered
            # from the pre-link declaration by location (finding U-1).
            getter = getattr(node, "getLocation", None)
            if getter is not None:
                recovered = self._model.declaration_at(getter())
                if recovered is not None:
                    doc = _docstring_of(recovered)
        return doc

    def _provenance(self, node: Any, owner_fileid: int) -> Provenance:
        """Where a member was written, relative to its owning type.

        A member merged from ``extend`` keeps its extend-site location, so a
        file other than the owning type's declaration file *is* the signal. No
        parser support is needed (enhancement plan section 1.1).
        """
        ref = self._source_ref(node)
        if ref is None:
            return Provenance()
        origin = (
            PROVENANCE_EXTENSION
            if owner_fileid >= 0 and ref.fileid != owner_fileid
            else PROVENANCE_DECLARATION
        )
        return Provenance(origin=origin, source=ref)

    def _skip(self, node: Any) -> bool:
        if is_synthesized(node):
            return True
        if not self._document_stdlib and self._fileid_of(node) == STDLIB_FILEID:
            return True
        return False

    def _qualname(self, parent: str, name: str) -> str:
        return f"{parent}::{name}" if parent else name

    # --- dispatch ----------------------------------------------------------

    def _build_node(self, node: Any, parent_qualname: str) -> PssObject | None:
        kind = node_type_name(node)
        handler = _DISPATCH.get(kind)
        if handler is None:
            return None
        if self._skip(node):
            return None
        return handler(self, node, parent_qualname)

    def _build_children(
        self, node: Any, qualname: str, owner_fileid: int
    ) -> list[PssObject]:
        children: list[PssObject] = []
        for child in iter_children(node):
            obj = self._build_node(child, qualname)
            if obj is None:
                continue
            obj.defined_in = self._provenance(child, owner_fileid)
            children.append(obj)
        return children

    # --- per-kind builders -------------------------------------------------

    def _build_scope(self, node: Any, parent_qualname: str) -> PssObject | None:
        """A ``SymbolScope`` — a package in the linked tree."""
        name = _name_of(node)
        if not name:
            return None
        qualname = self._qualname(parent_qualname, name)
        declaration = unwrap(node)

        obj = PssObject(
            kind="package",
            name=name,
            qualname=qualname,
            signature=f"package {name}",
            raw_doc=self._doc_for(node, declaration),
            annotations=_annotations_of(declaration),
            location=self._source_ref(node),
        )
        obj.children = self._build_children(node, qualname, self._fileid_of(node))
        return obj

    def _build_package_scope(self, node: Any, parent_qualname: str) -> PssObject | None:
        """A pre-link ``PackageScope`` — the degraded-mode form of a package.

        Named through ``getIdList()`` rather than ``getName()``, because PSS
        allows a qualified declaration (``package a::b { … }``).
        """
        id_list = getattr(node, "getIdList", lambda: None)()
        if id_list is None or not len(id_list):
            return None
        name = "::".join(str(node.getId(i).getId()) for i in range(len(id_list)))
        qualname = self._qualname(parent_qualname, name)

        obj = PssObject(
            kind="package",
            name=name,
            qualname=qualname,
            signature=f"package {name}",
            raw_doc=_docstring_of(node),
            annotations=_annotations_of(node),
            location=self._source_ref(node),
        )
        obj.children = self._build_children(node, qualname, self._fileid_of(node))
        return obj

    def _build_type_scope(self, node: Any, parent_qualname: str) -> PssObject | None:
        """A type: component, action, monitor, or one of the struct kinds.

        Handles both the linked form (a ``SymbolTypeScope`` wrapping the
        declaration) and the bare declaration reached in degraded mode —
        `unwrap` returns the node itself when there is no wrapper.
        """
        name = _name_of(node)
        if not name:
            return None
        qualname = self._qualname(parent_qualname, name)
        declaration = unwrap(node)
        decl_kind = node_type_name(declaration)

        if decl_kind == "Component":
            kind = "component"
        elif decl_kind == "Action":
            kind = "action"
        elif decl_kind == "Monitor":
            kind = "monitor"
        elif decl_kind == "Struct":
            struct_kind = getattr(declaration, "getKind", lambda: 1)()
            kind = STRUCT_KIND_TO_KIND.get(int(struct_kind), "struct")
        else:
            return None

        qualifiers: list[str] = []
        if getattr(declaration, "getIs_abstract", lambda: False)():
            qualifiers.append("abstract")

        extends = _type_identifier_name(
            getattr(declaration, "getSuper_t", lambda: None)()
        )
        template_params = _template_params_of(declaration)

        obj = PssObject(
            kind=kind,
            name=name,
            qualname=qualname,
            qualifiers=qualifiers,
            signature=render_type_signature(
                kind, name, qualifiers, template_params, extends
            ),
            extends=extends,
            template_params=template_params,
            raw_doc=self._doc_for(node, declaration),
            annotations=_annotations_of(declaration),
            location=self._source_ref(node),
        )
        obj.children = self._build_children(node, qualname, self._fileid_of(node))
        if kind == "action":
            obj.flow = _flow_spec_from_children(obj)
        return obj

    def _build_enum_scope(self, node: Any, parent_qualname: str) -> PssObject | None:
        name = _name_of(node)
        if not name:
            return None
        qualname = self._qualname(parent_qualname, name)

        obj = PssObject(
            kind="enum",
            name=name,
            qualname=qualname,
            signature=f"enum {name}",
            raw_doc=self._doc_for(node, unwrap(node)),
            annotations=_annotations_of(node),
            location=self._source_ref(node),
        )
        owner_fileid = self._fileid_of(node)
        obj.children = self._build_children(node, qualname, owner_fileid)
        if not obj.children:
            # A linked ``SymbolEnumScope`` exposes its values as children, but
            # a pre-link ``EnumDecl`` keeps them in a typed ``getItems()`` list.
            for item in _enum_items(node):
                built = self._build_enum_item(item, qualname)
                if built is not None:
                    built.defined_in = self._provenance(item, owner_fileid)
                    obj.children.append(built)
        return obj

    def _build_enum_item(self, node: Any, parent_qualname: str) -> PssObject | None:
        name = _name_of(node)
        if not name:
            return None
        return PssObject(
            kind="enum_item",
            name=name,
            qualname=self._qualname(parent_qualname, name),
            signature=name,
            raw_doc=_docstring_of(node),
            annotations=_annotations_of(node),
            location=self._source_ref(node),
        )

    def _build_function_scope(self, node: Any, parent_qualname: str) -> PssObject | None:
        """A ``SymbolFunctionScope``.

        The prototype carries neither a location nor a docstring (finding
        ``U-4``), so the definition supplies both and the prototype supplies
        only the signature.
        """
        definition = unwrap(node)
        proto = getattr(definition, "getProto", lambda: None)()
        if proto is None and node_type_name(definition) == "FunctionPrototype":
            proto = definition

        # In degraded mode the node *is* the ``FunctionDefinition``, which
        # carries no name of its own -- the prototype holds it.
        name = _name_of(node) or _name_of(proto)
        if not name:
            return None
        qualname = self._qualname(parent_qualname, name)

        qualifiers: list[str] = []
        if proto is not None:
            for accessor, keyword in (
                ("getIs_pure", "pure"),
                ("getIs_target", "target"),
                ("getIs_solve", "solve"),
            ):
                if getattr(proto, accessor, lambda: False)():
                    qualifiers.append(keyword)

        return PssObject(
            kind="function",
            name=name,
            qualname=qualname,
            qualifiers=qualifiers,
            signature=render_function_signature(name, qualifiers, proto),
            type_ref=_type_name(getattr(proto, "getRtype", lambda: None)())
            if proto is not None
            else None,
            raw_doc=_docstring_of(definition) or self._doc_for(node, definition),
            annotations=_annotations_of(definition),
            location=self._source_ref(node),
            children=_function_params(proto),
        )

    def _build_field(self, node: Any, parent_qualname: str) -> PssObject | None:
        if _is_builtin_field(node):
            return None
        name = _name_of(node)
        if not name:
            return None
        qualifiers = _qualifiers_of_field(node)
        type_name = _type_name(getattr(node, "getType", lambda: None)())

        return PssObject(
            kind="field",
            name=name,
            qualname=self._qualname(parent_qualname, name),
            qualifiers=qualifiers,
            signature=render_field_signature(name, qualifiers, type_name),
            type_ref=type_name,
            raw_doc=_docstring_of(node),
            annotations=_annotations_of(node),
            location=self._source_ref(node),
        )

    def _build_field_ref(self, node: Any, parent_qualname: str) -> PssObject | None:
        """An ``input`` / ``output`` flow-object reference."""
        name = _name_of(node)
        if not name:
            return None
        direction = "input" if getattr(node, "getIs_input", lambda: True)() else "output"
        type_name = _type_name(getattr(node, "getType", lambda: None)())

        return PssObject(
            kind="flow_ref",
            name=name,
            qualname=self._qualname(parent_qualname, name),
            qualifiers=[direction],
            signature=f"{direction} {type_name or '?'} {name}",
            type_ref=type_name,
            raw_doc=_docstring_of(node),
            annotations=_annotations_of(node),
            location=self._source_ref(node),
        )

    def _build_field_claim(self, node: Any, parent_qualname: str) -> PssObject | None:
        """A ``lock`` / ``share`` resource claim."""
        name = _name_of(node)
        if not name:
            return None
        mode = "lock" if getattr(node, "getIs_lock", lambda: True)() else "share"
        type_name = _type_name(getattr(node, "getType", lambda: None)())

        return PssObject(
            kind="resource_claim",
            name=name,
            qualname=self._qualname(parent_qualname, name),
            qualifiers=[mode],
            signature=f"{mode} {type_name or '?'} {name}",
            type_ref=type_name,
            raw_doc=_docstring_of(node),
            annotations=_annotations_of(node),
            location=self._source_ref(node),
        )

    def _build_pool(self, node: Any, parent_qualname: str) -> PssObject | None:
        name = _name_of(node)
        if not name:
            return None
        type_name = _type_name(getattr(node, "getType", lambda: None)())
        return PssObject(
            kind="pool",
            name=name,
            qualname=self._qualname(parent_qualname, name),
            signature=f"pool {type_name or '?'} {name}",
            type_ref=type_name,
            raw_doc=_docstring_of(node),
            location=self._source_ref(node),
        )

    def _build_constraint(self, node: Any, parent_qualname: str) -> PssObject | None:
        name = _name_of(node)
        if not name:
            # An anonymous constraint block has no name to reference and no
            # page of its own; its text belongs to the enclosing type.
            return None
        qualifiers = ["dynamic"] if getattr(node, "getIs_dynamic", lambda: False)() else []
        return PssObject(
            kind="constraint",
            name=name,
            qualname=self._qualname(parent_qualname, name),
            qualifiers=qualifiers,
            signature=f"constraint {name}",
            raw_doc=_docstring_of(node),
            annotations=_annotations_of(node),
            location=self._source_ref(node),
        )


def _enum_items(node: Any) -> list[Any]:
    """The ``EnumItem``\\ s of a pre-link ``EnumDecl``."""
    get_items = getattr(node, "getItems", None)
    if get_items is None:
        return []
    items = get_items()
    if items is None:
        return []
    return [node.getItem(i) for i in range(len(items))]


def _function_params(proto: Any) -> list[PssObject]:
    """Parameters of a function prototype, as ``field``-kind children."""
    if proto is None:
        return []
    get_params = getattr(proto, "getParameters", None)
    if get_params is None:
        return []
    params = get_params()
    result: list[PssObject] = []
    for i in range(len(params)):
        param = proto.getParameter(i)
        name = _name_of(param)
        if not name:
            continue
        type_name = _type_name(getattr(param, "getType", lambda: None)())
        result.append(
            PssObject(
                kind="field",
                name=name,
                qualname=name,
                signature=f"{type_name} {name}" if type_name else name,
                type_ref=type_name,
                raw_doc=_docstring_of(param),
            )
        )
    return result


def _flow_spec_from_children(action: PssObject) -> FlowSpec:
    """Assemble an action's `FlowSpec` from the members already built.

    Phase 2 replaces this with `sphinx_pss.model.flow`, which also resolves
    each reference to a qualified name and climbs inheritance. Doing the local
    part here means an action's flow signature is available from Phase 1, where
    the doc-field cross-validation needs it.
    """
    spec = FlowSpec()
    for member in action.children:
        if member.kind == "flow_ref":
            ref = FlowRef(
                name=member.name,
                type_name=member.type_ref or "?",
                direction=member.qualifiers[0] if member.qualifiers else "input",
            )
            (spec.inputs if ref.direction == "input" else spec.outputs).append(ref)
        elif member.kind == "resource_claim":
            claim = ResourceClaim(
                name=member.name,
                type_name=member.type_ref or "?",
                mode=member.qualifiers[0] if member.qualifiers else "lock",
            )
            (spec.locks if claim.mode == "lock" else spec.shares).append(claim)
    return spec


# --- signature rendering ----------------------------------------------------


def render_type_signature(
    kind: str,
    name: str,
    qualifiers: Iterable[str] = (),
    template_params: Iterable[TemplateParam] = (),
    extends: str | None = None,
) -> str:
    """Render a type declaration the way it appears in source."""
    parts = list(qualifiers) + [kind, name]
    text = " ".join(parts)
    params = list(template_params)
    if params:
        text += "<" + ", ".join(str(p) for p in params) + ">"
    if extends:
        text += f" : {extends}"
    return text


def render_field_signature(
    name: str, qualifiers: Iterable[str] = (), type_name: str | None = None
) -> str:
    """Render a field declaration: ``rand int len``, ``static const int n``."""
    parts = list(qualifiers)
    if type_name:
        parts.append(type_name)
    parts.append(name)
    return " ".join(parts)


def render_function_signature(
    name: str, qualifiers: Iterable[str] = (), proto: Any = None
) -> str:
    """Render a function prototype: ``int align_up(int n)``."""
    params: list[str] = []
    rtype: str | None = None
    if proto is not None:
        rtype = _type_name(getattr(proto, "getRtype", lambda: None)())
        get_params = getattr(proto, "getParameters", None)
        if get_params is not None:
            plist = get_params()
            for i in range(len(plist)):
                param = proto.getParameter(i)
                pname = _name_of(param) or ""
                ptype = _type_name(getattr(param, "getType", lambda: None)())
                params.append(f"{ptype} {pname}".strip() if ptype else pname)

    prefix = " ".join(list(qualifiers) + ([rtype] if rtype else ["void"]))
    return f"{prefix} {name}({', '.join(params)})"


#: Parser node type -> builder method. A node type absent from this table is
#: not documented, which is how Phase-2/3 kinds (activities, covergroups, exec
#: blocks) stay out of the Phase-1 output without a special case.
_DISPATCH = {
    # Linked forms -- the normal path.
    "SymbolScope": ModelBuilder._build_scope,
    "SymbolTypeScope": ModelBuilder._build_type_scope,
    "SymbolEnumScope": ModelBuilder._build_enum_scope,
    "SymbolFunctionScope": ModelBuilder._build_function_scope,
    # Pre-link declaration forms -- the degraded path
    # (``pss_tolerate_link_errors``). Members below are shared between the two.
    "PackageScope": ModelBuilder._build_package_scope,
    "Component": ModelBuilder._build_type_scope,
    "Action": ModelBuilder._build_type_scope,
    "Monitor": ModelBuilder._build_type_scope,
    "Struct": ModelBuilder._build_type_scope,
    "EnumDecl": ModelBuilder._build_enum_scope,
    "FunctionDefinition": ModelBuilder._build_function_scope,
    # Members.
    "EnumItem": ModelBuilder._build_enum_item,
    "Field": ModelBuilder._build_field,
    "FieldRef": ModelBuilder._build_field_ref,
    "FieldClaim": ModelBuilder._build_field_claim,
    "FieldPool": ModelBuilder._build_pool,
    "ConstraintBlock": ModelBuilder._build_constraint,
}


def build_objects(model: ParsedModel, *, document_stdlib: bool = False) -> list[PssObject]:
    """Convenience wrapper over `ModelBuilder`."""
    return ModelBuilder(model, document_stdlib=document_stdlib).build()
