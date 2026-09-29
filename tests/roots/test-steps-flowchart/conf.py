"""Step flowcharts over the Ethernet fixture (plan S4-TEST-1 and S4-TEST-3).

See ``test-autodoc/conf.py`` for why the fixture location comes from
``SPHINX_PSS_FIXTURES``. Tests choose the back-end with ``confoverrides``.
"""

import os
import pathlib

extensions = ["sphinx_pss"]

_FIXTURES = pathlib.Path(
    os.environ.get(
        "SPHINX_PSS_FIXTURES",
        pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "pss",
    )
)

pss_source_dirs = [str(_FIXTURES / "steps")]
graphviz_output_format = "svg"
