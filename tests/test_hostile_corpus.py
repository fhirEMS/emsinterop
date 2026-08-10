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

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from emsinterop import invariants
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
def test_satisfies_every_conversion_invariant(path, converted):
    """The shared rule set in `emsinterop.invariants` — the same checks the
    corpus sweep applies to tens of thousands of generated documents.

    These used to be spelled out here, which meant the sweep needed its own
    copy and the two would drift. One definition, two callers: this tier proves
    the rules hold for the cases we chose deliberately, the sweep proves it for
    the ones nobody thought of.
    """
    assert invariants.check(converted[path.stem]) == []


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_no_element_is_left_unmapped_at_all(path, converted):
    """Stricter than the shared rule, which only reports NATIONAL gaps. A
    hostile fixture is minimal and deliberate, so nothing in it should be
    deferred — including state and local elements."""
    assert converted[path.stem].issues.by_disposition(Disposition.UNMAPPED) == []


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


def test_symptom_onset_survives_without_any_condition(converted):
    """eSituation.01 with no impression and no chief complaint.

    Onset was read inside the primary-impression branch, so this document —
    legal NEMSIS, and the shape an unresponsive patient with a bystander-
    reported onset time produces — lost a national Required element silently.
    It now falls back to a standalone dated Observation, the same shape
    eSituation.18 (Last Known Well) already used."""
    result = converted["hostile_onset_no_impression"]
    assert not [r for r in result.resources if r["resourceType"] == "Condition"], \
        "fixture assumption: no Condition should be emitted"
    onset = [
        r for r in result.resources
        if r["resourceType"] == "Observation"
        and any(c.get("code") == "eSituation.01"
                for c in r.get("code", {}).get("coding", []))
    ]
    assert len(onset) == 1, "symptom onset was dropped"
    assert onset[0]["valueDateTime"] == "2026-08-06T13:40:00-06:00"
