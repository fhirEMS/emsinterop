"""Real-world NEMSIS samples — the field-hardening tier.

The golden corpus is six cases we authored ourselves, so it can only prove the
mapper handles what we thought of. These are the published NEMSIS v3.5.0
scenario samples (overdose, suicide, MVC, eBike, chest pain/MIH), authored by
someone else against the same standard — the closest thing to a real agency
export this project can test against.

They live outside the repo, so point EMSINTEROP_SAMPLES at the directory:

    EMSINTEROP_SAMPLES=/path/to/samples python -m pytest tests/test_nemsis_samples.py

What this tier locks in (each was a real defect these files exposed):
  - every sample XSD-validates and converts without an exception;
  - no NATIONAL element is left unmapped, and no issue is a warning — every
    leftover is a state/local element correctly dispositioned as deferred;
  - eVitals.07's XSD-sanctioned 'P'/'p' (palpated BP) survives as a systolic
    with an honestly-absent diastolic, rather than crashing the conversion.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from lxml import etree

from emsinterop.convert import convert
from emsinterop.ingest import validate
from emsinterop.issues import Disposition
from emsinterop.terminology import registry

SAMPLES = Path(os.environ.get("EMSINTEROP_SAMPLES", ""))
NEMSIS_NS = "http://www.nemsis.org"


def _is_nemsis_document(path: Path) -> bool:
    """Is this actually a NEMSIS EMSDataSet, by namespace?

    The tier globs *.xml so it can consume published samples AND generated
    corpora without assuming a filename convention. That breadth means a
    pointed-at directory may hold unrelated XML — the fhirEMSCore tree, for
    one, keeps a namespace-less hand-written stub next to the real samples.
    Judging by namespace rather than filename keeps out-of-scope files out
    without narrowing the glob back down."""
    try:
        return etree.parse(str(path)).getroot().tag == f"{{{NEMSIS_NS}}}EMSDataSet"
    except etree.XMLSyntaxError:
        return False


_ALL_XML = sorted(SAMPLES.glob("*.xml")) if SAMPLES.is_dir() else []
SAMPLE_FILES = [p for p in _ALL_XML if _is_nemsis_document(p)]
# Named, never silently dropped — the same discipline the mapper owes NEMSIS
# elements, the harness owes the files it was pointed at.
OUT_OF_SCOPE = [p.name for p in _ALL_XML if p not in SAMPLE_FILES]

pytestmark = pytest.mark.skipif(
    not SAMPLE_FILES,
    reason="set EMSINTEROP_SAMPLES to the NEMSIS sample directory to run this tier",
)


def test_out_of_scope_files_are_named_not_hidden():
    """If the pointed-at directory holds non-NEMSIS XML, say which files. A
    harness that quietly ignores input is the same failure mode as a mapper
    that quietly drops an element."""
    if OUT_OF_SCOPE:
        pytest.skip(f"not NEMSIS EMSDataSet documents, excluded: {OUT_OF_SCOPE}")


@pytest.fixture(scope="module")
def converted():
    return {p.stem: convert(p)[0] for p in SAMPLE_FILES}


@pytest.mark.parametrize("path", SAMPLE_FILES, ids=lambda p: p.stem)
def test_sample_is_xsd_valid(path):
    assert validate(path) == []


@pytest.mark.parametrize("path", SAMPLE_FILES, ids=lambda p: p.stem)
def test_sample_converts(path, converted):
    result = converted[path.stem]
    assert result.resources, "conversion produced no resources"
    assert result.context.pcr_number
    # The document projection must close its reference graph too.
    assert result.document["entry"]


@pytest.mark.parametrize("path", SAMPLE_FILES, ids=lambda p: p.stem)
def test_no_national_element_is_unmapped(path, converted):
    """The national dataset is what this project claims to cover; real files
    must not turn up gaps in it."""
    result = converted[path.stem]
    unmapped = result.issues.by_disposition(Disposition.UNMAPPED)
    national = [i.element_id for i in unmapped if registry.is_national(i.element_id)]
    assert national == [], f"national elements left unmapped: {sorted(set(national))}"


@pytest.mark.parametrize("path", SAMPLE_FILES, ids=lambda p: p.stem)
def test_every_issue_is_informational(path, converted):
    """Real exports carry many state/local elements. They must be ledgered as
    deferrals (information), never as warnings — otherwise the issue log cries
    wolf and the genuine signals get lost."""
    result = converted[path.stem]
    loud = [(i.element_id, i.severity, i.reason) for i in result.issues.issues
            if i.severity != "information"]
    assert loud == [], f"non-informational issues: {loud[:6]}"


def test_palpated_blood_pressure_survives(converted):
    """eVitals.07 'P'/'p' — a palpated BP, routine on hypotensive patients.
    It used to raise ValueError and abort the whole PCR.

    Skipped when the pointed-at corpus contains no palpated BP: this asserts a
    property of the PUBLISHED samples, and the tier also runs over generated
    corpora that may not contain one. The permanent guard is the in-repo
    hostile fixture, which always runs."""
    palpated = []
    for result in converted.values():
        for obs in result.resources:
            if obs["resourceType"] != "Observation":
                continue
            if not any(c.get("code") == "85354-9"
                       for c in obs.get("code", {}).get("coding", [])):
                continue
            components = {
                c["code"]["coding"][0]["code"]: c for c in obs.get("component", [])
            }
            diastolic = components.get("8462-4", {})
            reason = (diastolic.get("dataAbsentReason", {}).get("coding") or [{}])[0]
            if reason.get("code") == "not-performed":
                palpated.append((obs, components))

    if not palpated:
        pytest.skip("this corpus contains no palpated BP")
    obs, components = palpated[0]
    # Systolic is real data and must be preserved, not discarded with the pair.
    assert components["8480-6"]["valueQuantity"]["value"] > 0
    assert "valueQuantity" not in components["8462-4"]
    assert obs["method"]["text"] == "Palpated"
