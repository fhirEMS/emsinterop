from pathlib import Path

import pytest

from emsinterop.convert import convert
from emsinterop.ingest import parse

FIXTURES = Path(__file__).parent / "fixtures"
CHEST_PAIN = FIXTURES / "pcr_chest_pain.xml"


@pytest.fixture(scope="session")
def dataset():
    return parse(CHEST_PAIN)


@pytest.fixture(scope="session")
def result():
    return convert(CHEST_PAIN)[0]


@pytest.fixture(scope="session")
def resources(result):
    return result.resources


def by_type(resources, resource_type):
    return [r for r in resources if r["resourceType"] == resource_type]


@pytest.fixture(scope="session")
def fixture_path():
    return CHEST_PAIN


# Optional sibling: the ccda rail's renderer (the nemsis2CCDA checkout
# nests inside this repo; its conftest resolves us the same way). Harmless when absent — the rail reports its unavailability.
import sys as _sys
_ccda_src = Path(__file__).resolve().parents[1] / "nemsis2CCDA" / "src"
if _ccda_src.exists() and str(_ccda_src) not in _sys.path:
    _sys.path.insert(0, str(_ccda_src))
