"""Step tables over the Ethernet fixture, in every directive form (plan S3-TEST-1).

The fixture directory is given as a source directory, so the Source column
shows paths relative to it (``eth_mac.pss:35``). See ``test-autodoc/conf.py``
for why the location comes from ``SPHINX_PSS_FIXTURES``.
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
