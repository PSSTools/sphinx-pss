"""``:activity-diagram:`` on the autopss directives (activity-diagrams plan AD3-TEST-1).

See ``test-autodoc/conf.py`` for why the fixture location comes from
``SPHINX_PSS_FIXTURES``. Tests set ``pss_default_options`` with
``confoverrides``; outlines keep the tests independent of Graphviz.
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

pss_source_files = [str(_FIXTURES / "activities" / "xfer_pkg.pss")]
