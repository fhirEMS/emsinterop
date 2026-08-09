"""The hostile corpus — XSD-VALID input the mapper must survive.

The golden corpus is six cases we authored, so it only proves the mapper
handles what we thought of. Real NEMSIS exports carry things we didn't: a
blood pressure recorded as palpated, a glucose meter reporting "High", a sex
the patient refused to state, a comment sitting inside a value, a PCR number
with a slash in it. Every one of those is legal against the pinned 3.5.0
schema, and each one of them was a real defect before it was a fixture here.

The rule for this directory: **every fixture must XSD-validate**. A fixture
that fails the schema belongs in the quarantine tests instead — the point of
this tier is input the gate lets through.

These run in default CI (no env gate), unlike `test_nemsis_samples.py` which
needs external files. Fixtures live in a subdirectory so they stay invisible
to the seven `FIXTURES.glob("*.xml")` sweeps that pin golden-corpus promises a
hostile case shouldn't have to keep.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from emsinterop.convert import convert
from emsinterop.ingest import validate
from emsinterop.issues import Disposition
from emsinterop.mapping import common

HOSTILE = Path(__file__).parent / "fixtures" / "hostile"
FIXTURES = sorted(HOSTILE.glob("*.xml"))

assert FIXTURES, "the hostile corpus is empty — fixtures missing?"


@pytest.fixture(scope="module")
def converted():
    return {p.stem: convert(p)[0] for p in FIXTURES}


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_is_xsd_valid(path):
    """The tier's own contract: these are LEGAL documents, not malformed ones."""
    assert validate(path) == []


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_converts_without_raising(path, converted):
    result = converted[path.stem]
    assert result.resources and result.document["entry"]


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_nothing_is_silently_dropped(path, converted):
    """The #1 hard rule. Every source element is consumed by a mapper or
    ledgered — hostile input must not open a third path."""
    result = converted[path.stem]
    present = result.context.pcr.element_ids()
    flagged = {i.element_id for i in result.issues.issues}
    assert present - result.context.consumed - flagged == set()
    assert result.issues.by_disposition(Disposition.UNMAPPED) == []


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_output_is_serializable_json(path, converted):
    """`allow_nan=False` is the generic guard: NaN/Infinity are valid Python
    floats but INVALID JSON, so one leak anywhere in the graph makes the whole
    bundle unparseable by any conforming server."""
    result = converted[path.stem]
    json.dumps(result.transaction, allow_nan=False)
    json.dumps(result.document, allow_nan=False)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_conditional_update_urls_are_well_formed(path, converted):
    """A PCR number is xs:string with no pattern, so it can carry /, &, ?, #.
    Those must not leak into the request URL's structure — an unescaped `?`
    would truncate the search and could match the WRONG resource."""
    result = converted[path.stem]
    for entry in result.transaction["entry"]:
        url = entry["request"]["url"]
        # Structural characters must appear only where they are structure. We
        # assert on the RAW url, not on parse_qs output — parse_qs percent-
        # DECODES, so a correctly-escaped value legitimately contains '?' once
        # decoded and checking there would test nothing.
        assert "#" not in url, f"unescaped fragment marker in request URL: {url}"
        assert url.count("?") <= 1, f"unescaped query marker in request URL: {url}"
        assert urlsplit(url).fragment == ""


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_vital_signs_conformance(path, converted):
    """Two US Core invariants, checked structurally so any future fixture is
    covered automatically:

    vs-1 — a vital-signs Observation must not carry a value-less
    `_effectiveDateTime`; the validator applies the base vitalsigns profile on
    the strength of `category`, not `meta.profile`, so the element has to be
    omitted entirely, not merely stripped of its profile claim.

    And a profile is only claimed when it can actually be met.
    """
    result = converted[path.stem]
    for obs in result.resources:
        if obs.get("resourceType") != "Observation":
            continue
        categories = {
            coding.get("code")
            for concept in obs.get("category", [])
            for coding in concept.get("coding", [])
        }
        if "vital-signs" not in categories:
            continue
        assert "_effectiveDateTime" not in obs, (
            f"{obs['id']} carries a value-less effective time (vs-1)")
        claims = obs.get("meta", {}).get("profile", [])
        if any("vital-signs" in c or "blood-pressure" in c for c in claims):
            assert common.can_claim_vital_signs(obs), (
                f"{obs['id']} claims a vital-signs profile it cannot satisfy")


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_us_core_patient_claim_is_earned(path, converted):
    """us-core-patient requires gender (min 1). A data-absent extension does
    NOT satisfy that, so the claim must be withheld rather than asserted —
    and we never invent a gender to satisfy a validator."""
    result = converted[path.stem]
    for patient in result.resources:
        if patient.get("resourceType") != "Patient":
            continue
        if any("us-core-patient" in c
               for c in patient.get("meta", {}).get("profile", [])):
            assert isinstance(patient.get("gender"), str), (
                "us-core-patient claimed without a gender value")


# -- what each fixture specifically pins --------------------------------------

def test_comment_inside_a_value_does_not_destroy_it(converted):
    """lxml counts comments as children, so a naive group/leaf test turns a
    valued element into an empty group and the reading vanishes."""
    result = converted["hostile_comment_in_value"]
    systolics = [
        component["valueQuantity"]["value"]
        for obs in result.resources
        if obs.get("resourceType") == "Observation"
        for component in obs.get("component", [])
        if component["code"]["coding"][0]["code"] == "8480-6"
        and "valueQuantity" in component
    ]
    assert 124 in systolics, "systolic 124 was lost to the comment"


def test_glucose_high_is_a_reading_not_malformed_data(converted):
    """eVitals.18 permits High/Low per the XSD — an off-scale meter result.
    Recording it as 'error' would turn a clinical finding into a data fault."""
    result = converted["hostile_glucose_high"]
    glucose = [o for o in result.resources
               if o.get("resourceType") == "Observation"
               and any(c.get("code") == "2339-0"
                       for c in o.get("code", {}).get("coding", []))]
    assert glucose, "no glucose observation emitted"
    obs = glucose[0]
    assert "valueQuantity" not in obs
    codes = {c["code"] for c in obs["dataAbsentReason"]["coding"]}
    assert "not-a-number" in codes
    interpretations = {
        c["code"]
        for concept in obs.get("interpretation", [])
        for c in concept.get("coding", [])
    }
    # '>' is "above the maximum quantifiable limit" — what a meter's "High"
    # means. HX would assert a clinical alert threshold the source never stated.
    assert ">" in interpretations, "off-scale-high not recorded as an interpretation"


def test_uppercase_uuid_yields_the_same_ids_as_lowercase(converted):
    """The NEMSIS UUID pattern allows [a-fA-F0-9], so the same record re-exported
    with different casing must still update in place, not duplicate."""
    import re

    from emsinterop.convert import convert as _convert

    upper = converted["hostile_uppercase_uuid"]
    source = (HOSTILE / "hostile_uppercase_uuid.xml").read_text()
    lowered = re.sub(r'UUID="([^"]*)"',
                     lambda m: f'UUID="{m.group(1).lower()}"', source)
    lower = _convert(lowered.encode())[0]
    assert [r["id"] for r in upper.resources] == [r["id"] for r in lower.resources]


def test_url_unsafe_pcr_number_survives_round_trip(converted):
    """The identifier must come back out of the request URL byte-identical."""
    result = converted["hostile_url_unsafe_id"]
    pcr_number = result.context.pcr_number
    assert "/" in pcr_number and "&" in pcr_number  # fixture assumption
    seen = False
    for entry in result.transaction["entry"]:
        url = entry["request"]["url"]
        if "Composition?identifier=" not in url:
            continue
        seen = True
        # parse_qs decodes, so this proves the escape/unescape round-trips
        # back to the exact source identifier — no truncation, no mangling.
        (raw,) = parse_qs(urlsplit(url).query)["identifier"]
        _, _, value = raw.rpartition("|")
        assert value == pcr_number, f"{value!r} != {pcr_number!r}"
    assert seen, "no Composition conditional-update URL to check"
