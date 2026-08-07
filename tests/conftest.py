from pathlib import Path

import pytest

from nemsis2fhir.convert import convert
from nemsis2fhir.ingest import parse

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
