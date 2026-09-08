"""P0 smoke test — proves the package installs and CI is wired correctly.

Delete this once real unit tests exist for C1 (property model) modules.
"""

import fabchem


def test_package_has_version():
    assert fabchem.__version__ == "0.0.0"
