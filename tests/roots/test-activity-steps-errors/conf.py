"""Steps in activities (activity-diagrams plan AD4-TEST-3).

See ``test-autodoc/conf.py`` for why the fixture location comes from
``SPHINX_PSS_FIXTURES``. Outlines keep most tests independent of Graphviz.
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

pss_source_files = [str(_FIXTURES / "activities" / "steps_xfer.pss")]
pss_diagrams = "off"
