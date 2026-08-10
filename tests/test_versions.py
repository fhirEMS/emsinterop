"""NEMSIS release compatibility and FHIR dateTime legality."""

import glob

import pytest

from emsinterop.ingest.xsd import (
    PINNED_VERSION,
    SUPPORTED_VERSIONS,
    resolve_version,
    validate_dataset,
)
from emsinterop.mapping.common import fhir_datetime

CORPUS = sorted(glob.glob("tests/fixtures/pcr_*.xml")) + sorted(
    glob.glob("tests/fixtures/hostile/*.xml"))


@pytest.mark.parametrize("version", SUPPORTED_VERSIONS)
@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.rsplit("/", 1)[-1])
def test_corpus_validates_against_every_supported_release(path, version):
    """3.5.1's XSDs differ from 3.5.0's by one line — ePatient.25 gains an
    explicit minOccurs="1", which is XSD's default. So a document valid under
    one must be valid under the other; this proves it rather than assuming."""
    assert validate_dataset(path, "EMSDataSet", version) == []


def test_unknown_release_falls_back_to_the_pinned_one():
    """We do not guess forward: a future release validates against the pinned
    schemas so a real difference surfaces as an error, not silent acceptance."""
    assert resolve_version("3.5.1") == "3.5.1"
    assert resolve_version("3.5.0") == "3.5.0"
    assert resolve_version("3.9.9") == PINNED_VERSION
    assert resolve_version(None) == PINNED_VERSION


@pytest.mark.parametrize(
    "value,expected",
    [
        # xs:dateTime allows hour 24 (end of day); FHIR caps hours at 23, so an
        # XSD-valid NEMSIS timestamp would fail every FHIR validator.
        ("2026-08-06T24:00:00-06:00", "2026-08-07T00:00:00-06:00"),
        ("2026-12-31T24:00:00Z", "2027-01-01T00:00:00Z"),       # year rollover
        ("2026-02-28T24:00:00-06:00", "2026-03-01T00:00:00-06:00"),  # month end
        ("2026-08-06T09:07:00-06:00", "2026-08-06T09:07:00-06:00"),  # untouched
        ("2026-08-06", "2026-08-06"),
        (None, None),
    ],
)
def test_hour_24_is_normalized(value, expected):
    assert fhir_datetime(value) == expected
