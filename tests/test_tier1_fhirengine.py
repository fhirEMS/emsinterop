"""Tier-1 validation harness: the golden corpus against a LIVE fhirEngine.

Skipped unless NEMSIS2FHIR_TIER1_URL points at a running fhirEngine with
US Core 6.1.0 installed and FHIRENGINE_VALIDATION_PROFILES=declared
(see scripts/tier1-up.sh). This is the submission gate of Architecture §5.5b;
the external HL7 validator (Tier-2) stays authoritative for mPSC/IPS.
"""

import os

import pytest

from nemsis2fhir.convert import convert
from nemsis2fhir.submit import FhirEngineClient

from .conftest import FIXTURES

TIER1_URL = os.environ.get("NEMSIS2FHIR_TIER1_URL")
AGENCY_NAMES = {"4901": "Wasatch Valley EMS (synthetic)"}

pytestmark = pytest.mark.skipif(
    not TIER1_URL, reason="set NEMSIS2FHIR_TIER1_URL to run Tier-1 against fhirEngine"
)

ALL_FIXTURES = sorted(FIXTURES.glob("*.xml"))


@pytest.fixture(scope="module")
def client():
    c = FhirEngineClient(TIER1_URL)
    yield c
    c.close()


def _statuses(response: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in response.get("entry", []):
        status = entry.get("response", {}).get("status", "?")
        counts[status] = counts.get(status, 0) + 1
    return counts


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_corpus_passes_tier1(client, path):
    """Every corpus transaction is accepted; every entry succeeds (2xx)."""
    result = convert(path, agency_names=AGENCY_NAMES)[0]
    response = client.submit(result.transaction)  # raises SubmissionError on 4xx/5xx
    statuses = _statuses(response)
    non_2xx = {s: n for s, n in statuses.items() if not s.startswith("2")}
    assert non_2xx == {}, f"non-2xx entries: {non_2xx}"


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_resubmission_is_idempotent(client, path):
    """Second submission updates every resource in place — no duplicates."""
    result = convert(path, agency_names=AGENCY_NAMES)[0]
    client.submit(result.transaction)
    response = client.submit(result.transaction)
    statuses = _statuses(response)
    assert set(statuses) == {"200"}, f"expected all updates, got {statuses}"
