# Diagrams

Diagrams are drawn from the model at build time, so they change when the code
does. There are two kinds: the {ref}`step flowchart <step-flowcharts>` and the
{doc}`activity diagram <activities>`. Flow and component diagrams will use the
same back-end and the same settings.

## Choosing a back-end

`pss_diagrams` in `conf.py` picks what draws them:

| Value | Draws with | Needs |
|---|---|---|
| `"graphviz"` (default) | `sphinx.ext.graphviz`, which comes with Sphinx and is loaded by `sphinx-pss` | Graphviz's `dot` command on the build machine |
| `"mermaid"` | [`sphinxcontrib-mermaid`](https://pypi.org/project/sphinxcontrib-mermaid/), in the reader's browser | The package, and `"sphinxcontrib.mermaid"` in `extensions` |
| `"off"` | Nothing | Nothing |

```python
# conf.py
pss_diagrams = "graphviz"
```

### Graphviz

Install Graphviz with the system's package manager: `apt install graphviz`,
`dnf install graphviz` or `brew install graphviz`. If `dot` isn't on the
`PATH`, name it with `sphinx.ext.graphviz`'s `graphviz_dot` setting.

Diagrams are SVG or PNG, as `graphviz_output_format` says; it defaults to
`png`. Links work in both, since Sphinx gives a PNG a clickable image map. SVG
stays sharp at any zoom, so it is the better choice for diagrams:

```python
graphviz_output_format = "svg"
```

### Mermaid

Mermaid needs no `dot`, which suits hosts where you can't install it. The
diagrams are drawn by JavaScript when the page loads, so they appear only in
HTML output.

```python
# conf.py
extensions = ["sphinx_pss", "sphinxcontrib.mermaid"]
pss_diagrams = "mermaid"
```

Mermaid ignores links unless its security level allows them. To make a
diagram's boxes clickable, set:

```python
mermaid_init_config = {"startOnLoad": False, "securityLevel": "loose"}
```

This is the flowchart of `set_speed` from the previous page, as `sphinx-pss`
writes it for Mermaid:

```{code-block} text
:name: diagram-example-mermaid

flowchart TD
    n1(["Start"])
    n2["1 Program the speed"]
    n3{"speed"}
    n4["1.1 Select 10 Mbps"]
    n5["1.2 Select 100 Mbps"]
    n6["2 Poll the PHY until the link is<br/>up"]
    n7["2.1 Read the PHY status"]
    n8{"(read_reg(0x2A0) #38;<br/>0x4) == 0"}
    n9["3 Settle"]
    n10{{"Repeat retries times"}}
    n11["3.1 Wait one MDC period"]
    n12(["End"])
    n1 --> n2
    n2 --> n3
    n3 -->|"SPEED_10"| n4
    n3 -->|"SPEED_100"| n5
    n4 --> n6
    n5 --> n6
    n6 --> n7
    n7 --> n8
    n8 -->|"yes"| n7
    n8 -->|"no"| n9
    n9 --> n10
    n10 --> n11
    n11 --> n10
    n10 -->|"done"| n12
```

## When a diagram can't be drawn

A missing `dot`, or `"mermaid"` without its extension, doesn't fail the
build. The first page that asks for a diagram gets one warning for the whole
build, and each diagram is left out:

```text
steps.md:12: WARNING: sphinx-pss: Graphviz's 'dot' command was not found (graphviz_dot), so diagrams are left out. Install Graphviz, or set pss_diagrams = 'mermaid' or 'off' [pss.diagrams]
```

A step flowchart is replaced by its step table, and an activity diagram by
its outline, so the page still shows the procedure or the activity. `"off"` does the same without a warning. To keep the warning out of
a `-W` build on a machine without Graphviz, suppress it:

```python
suppress_warnings = ["pss.diagrams"]
```

## Stable output

Diagrams come out the same on every build of the same source: node order and
names follow the source, not the order of a hash table. Sphinx names each
Graphviz image after a hash of its text, so an unchanged diagram keeps its
file name, and a diff of two builds shows only the diagrams that changed.
