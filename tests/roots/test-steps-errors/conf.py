"""Every way a step table can be asked for wrongly (plan S3-TEST-5).

Not built under ``-W``: each directive here is an error, reported at its
line of ``index.rst``, which is where the mistake is. See
``test-autodoc/conf.py`` for why the fixtures come from ``SPHINX_PSS_FIXTURES``.
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
