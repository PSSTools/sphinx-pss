"""A Pygments lexer for PSS.

Pygments has no PSS lexer, so without this every ``pss`` code block — in a
project's own prose, in this project's docs, and in the source listings
``viewcode`` will generate — either fails the build under ``-W`` or renders as
plain text.

The keyword set is taken from ``pssparser``'s ``src/PSSLexer.g4`` so the two
cannot drift apart silently: anything the parser treats as a keyword is
highlighted as one.

.. note::

   **This is an interim home.** Resolved 2026-08-13: the PSS lexer becomes its
   own package, so that MkDocs, ``pygmentize`` and plain docutils can use it
   too and so that the ``pss`` alias has a single owner. When that package
   exists, ``sphinx-pss`` should depend on it and this module should be
   deleted along with its ``app.add_lexer`` registration.

   It stays here until then because without it a ``pss`` code block fails any
   ``-W`` build — Pygments ships no PSS lexer — which would hit every project
   that documents PSS carefully, including this one.
"""

from __future__ import annotations

from pygments.lexer import RegexLexer, bygroups, words
from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
)

#: Declaration keywords whose operand is another keyword rather than a
#: user-chosen name: ``exec body``, ``activity { … }``. Excluded from the
#: "keyword then name" rule, which would otherwise highlight the exec kind as
#: though it were a declared type.
UNNAMED_DECLARATION_KEYWORDS = ("activity", "exec")

#: Type-declaring keywords — the things a documented object can be.
DECLARATION_KEYWORDS = (
    "action",
    "activity",
    "annotation",
    "buffer",
    "component",
    "covergroup",
    "coverpoint",
    "cross",
    "enum",
    "exec",
    "function",
    "monitor",
    "package",
    "pool",
    "resource",
    "state",
    "stream",
    "struct",
    "typedef",
)

#: Built-in types.
TYPE_KEYWORDS = (
    "array",
    "bit",
    "bool",
    "chandle",
    "float32",
    "float64",
    "int",
    "list",
    "map",
    "set",
    "string",
    "void",
)

#: Declaration modifiers and qualifiers.
QUALIFIER_KEYWORDS = (
    "abstract",
    "const",
    "dynamic",
    "export",
    "import",
    "instance",
    "mutable",
    "override",
    "private",
    "protected",
    "public",
    "pure",
    "rand",
    "ref",
    "static",
    "symbol",
    "target",
    "type",
)

#: Everything else the grammar reserves: statements, activity constructs,
#: flow/resource declarations, coverage, and exec-block kinds.
KEYWORDS = (
    "as",
    "assert",
    "bind",
    "bins",
    "body",
    "break",
    "class",
    "compile",
    "concat",
    "constraint",
    "continue",
    "declaration",
    "default",
    "disable",
    "dist",
    "do",
    "else",
    "eventually",
    "extend",
    "file",
    "forall",
    "foreach",
    "from",
    "has",
    "header",
    "if",
    "iff",
    "ignore_bins",
    "illegal_bins",
    "in",
    "init",
    "init_down",
    "init_up",
    "inout",
    "input",
    "join_branch",
    "join_first",
    "join_none",
    "join_select",
    "lock",
    "match",
    "numeric",
    "option",
    "output",
    "overlap",
    "parallel",
    "post_solve",
    "pre_solve",
    "pyimport",
    "pyobj",
    "randomize",
    "repeat",
    "replicate",
    "return",
    "run_end",
    "run_start",
    "schedule",
    "select",
    "sequence",
    "share",
    "solve",
    "super",
    "unique",
    "while",
    "with",
    "yield",
)

#: Literals.
CONSTANT_KEYWORDS = ("true", "false", "null")


class PssLexer(RegexLexer):
    """Highlights Accellera PSS source."""

    name = "PSS"
    aliases = ["pss"]
    filenames = ["*.pss"]
    mimetypes = ["text/x-pss"]
    url = "https://accellera.org/downloads/standards/portable-stimulus"

    tokens = {
        "root": [
            (r"\s+", Text),
            # Comments. Doc-comment forms are highlighted distinctly, since in
            # a PSS project they are documentation rather than an aside.
            (r"//[/!].*?$", Comment.Special),
            (r"//.*?$", Comment.Single),
            (r"/\*[*!](?!/)", Comment.Special, "docblock"),
            (r"/\*", Comment.Multiline, "block"),
            # Annotations: @doc {.text = "..."} and the pssparser paren form.
            (r"(@)([A-Za-z_]\w*)", bygroups(Name.Decorator, Name.Decorator)),
            # Strings.
            (r'"""', String, "tripledoublequote"),
            (r'"', String, "doublequote"),
            # Numbers, including PSS/Verilog sized literals such as 8'hFF.
            (r"\d*'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ_?]+", Number),
            (r"0[xX][0-9a-fA-F_]+", Number.Hex),
            (r"0[bB][01_]+", Number.Bin),
            (r"\d[\d_]*\.\d[\d_]*([eE][+-]?\d+)?", Number.Float),
            (r"\d[\d_]*", Number.Integer),
            # Keyword groups, longest-first so 'init_down' beats 'init'.
            (words(CONSTANT_KEYWORDS, suffix=r"\b"), Keyword.Constant),
            (words(TYPE_KEYWORDS, suffix=r"\b"), Keyword.Type),
            (words(QUALIFIER_KEYWORDS, suffix=r"\b"), Keyword.Declaration),
            # A declaration keyword followed by a name: highlight the name too,
            # which is what a reader is scanning for in a documentation page.
            (
                r"\b(%s)(\s+)([A-Za-z_]\w*)"
                % "|".join(
                    sorted(
                        (
                            k
                            for k in DECLARATION_KEYWORDS
                            if k not in UNNAMED_DECLARATION_KEYWORDS
                        ),
                        key=len,
                        reverse=True,
                    )
                ),
                bygroups(Keyword.Declaration, Text, Name.Class),
            ),
            (words(DECLARATION_KEYWORDS, suffix=r"\b"), Keyword.Declaration),
            (words(KEYWORDS, suffix=r"\b"), Keyword),
            # Qualified names.
            (r"([A-Za-z_]\w*)(\s*)(::)", bygroups(Name.Namespace, Text, Operator)),
            (r"[A-Za-z_]\w*", Name),
            (r"[{}()\[\];,.]", Punctuation),
            (r"[-+*/%!~^&|<>=?:]+", Operator),
        ],
        "block": [
            (r"[^*/]+", Comment.Multiline),
            (r"\*/", Comment.Multiline, "#pop"),
            (r"[*/]", Comment.Multiline),
        ],
        "docblock": [
            (r"[^*/]+", Comment.Special),
            (r"\*/", Comment.Special, "#pop"),
            (r"[*/]", Comment.Special),
        ],
        "doublequote": [
            (r'\\.', String.Escape),
            (r'"', String, "#pop"),
            (r'[^\\"]+', String),
        ],
        "tripledoublequote": [
            (r'"""', String, "#pop"),
            (r'[^"]+', String),
            (r'"', String),
        ],
    }
