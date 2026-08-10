"""The invariant rules, proved non-vacuous.

A rule that cannot fail is worse than no rule: it reports "clean" forever and
nobody looks again. The corpus sweep currently finds nothing across tens of
thousands of documents, and the only thing separating that from a broken
harness is this file — each rule is handed input that breaks it and must say
so, and handed input that satisfies it and must stay quiet.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from emsinterop import invariants
from emsinterop.convert import convert
from emsinterop.issues import Disposition


def make_result(resources=None, transaction=None, document=None,
                present=(), consumed=(), issues=()):
    """A minimal stand-in for a ConversionResult.

    Hand-built rather than converted from a fixture: to prove a rule fires we
    need input that VIOLATES it, and every real fixture is (by design) clean.
    """
    pcr = SimpleNamespace(element_ids=lambda: set(present))
    return SimpleNamespace(
        resources=list(resources or []),
        transaction=transaction if transaction is not None else {"entry": []},
        document=document if document is not None else {"entry": []},
        context=SimpleNamespace(pcr=pcr, consumed=set(consumed)),
        issues=SimpleNamespace(
            issues=list(issues),
            by_disposition=lambda d: [i for i in issues if i.disposition == d],
        ),
    )


def issue(element_id, disposition=Disposition.UNMAPPED):
    return SimpleNamespace(element_id=element_id, disposition=disposition,
                           severity="warning", reason="")


def test_clean_result_produces_no_violations():
    """The control: without it, a rule that fires on everything would look
    like a rule that works."""
    assert invariants.check(make_result()) == []


def test_silently_dropped_element_is_caught():
    result = make_result(present={"eVitals.06"}, consumed=set(), issues=[])
    rules = {v.rule for v in invariants.check(result)}
    assert "element-dropped-silently" in rules
    # Consumed or ledgered are both acceptable; only the third path is a defect.
    assert not invariants.check_nothing_dropped(
        make_result(present={"eVitals.06"}, consumed={"eVitals.06"}))
    assert not invariants.check_nothing_dropped(
        make_result(present={"eVitals.06"}, issues=[issue("eVitals.06")]))


def test_unmapped_national_element_is_caught():
    """eSituation.01 is national; a state/local element is a legitimate
    deferral and must NOT be reported."""
    caught = invariants.check_no_unmapped_national(
        make_result(issues=[issue("eSituation.01")]))
    assert [v.rule for v in caught] == ["national-element-unmapped"]
    assert not invariants.check_no_unmapped_national(
        make_result(issues=[issue("eOther.99")]))


def test_nan_is_caught_because_it_is_invalid_json():
    """NaN is a valid Python float and invalid JSON: one leak makes the whole
    bundle unparseable by any conforming server."""
    result = make_result(transaction={"entry": [{"v": float("nan")}]})
    assert [v.rule for v in invariants.check_json_serializable(result)] == \
        ["json-not-serializable"]


@pytest.mark.parametrize("url,rule", [
    ("Patient?identifier=sys|a#b", "url-unescaped-fragment"),
    ("Patient?identifier=sys|a?rev=2", "url-unescaped-query"),
])
def test_unescaped_url_structure_is_caught(url, rule):
    """An unescaped `?` truncates the search and could match the WRONG
    patient's resource — a silent mis-write, not an error."""
    result = make_result(transaction={"entry": [{"request": {"url": url}}]})
    assert rule in {v.rule for v in invariants.check_request_urls(result)}


def test_valueless_effective_time_on_a_vital_sign_is_caught():
    """vs-1. The validator applies the vitalsigns profile on the strength of
    `category`, not `meta.profile`, so the element must be omitted entirely."""
    vital = {
        "resourceType": "Observation", "id": "o1",
        "category": [{"coding": [{"code": "vital-signs"}]}],
        "_effectiveDateTime": {"extension": []},
    }
    assert [v.rule for v in invariants.check_vital_signs_conformance(
        make_result([vital]))] == ["vs-1-valueless-effective"]
    # A value alongside the extension is how reduced precision is carried.
    vital["effectiveDateTime"] = "2026-08-06"
    assert not invariants.check_vital_signs_conformance(make_result([vital]))


def test_unearned_us_core_patient_claim_is_caught():
    """us-core-patient requires gender (min 1); a data-absent extension does
    not satisfy it. The fix is to withhold the claim, never to invent a value."""
    patient = {
        "resourceType": "Patient", "id": "p1",
        "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]},
        "_gender": {"extension": []},
    }
    assert [v.rule for v in invariants.check_profile_claims_are_earned(
        make_result([patient]))] == ["profile-claim-unearned"]
    patient["gender"] = "unknown"
    assert not invariants.check_profile_claims_are_earned(make_result([patient]))


def test_dangling_reference_is_caught():
    """A broken graph survives JSON validity and profile checks all the way to
    a server."""
    resources = [
        {"resourceType": "Observation", "id": "o1",
         "subject": {"reference": "Patient/does-not-exist"}},
    ]
    assert [v.rule for v in invariants.check_references_resolve(
        make_result(resources))] == ["reference-unresolved"]
    resources.append({"resourceType": "Patient", "id": "does-not-exist"})
    assert not invariants.check_references_resolve(make_result(resources))


def test_absolute_and_contained_references_are_not_our_problem():
    """Only relative Type/id references are ours to close; flagging the others
    would make the rule noisy and it would get switched off."""
    resources = [{
        "resourceType": "Observation", "id": "o1",
        "a": {"reference": "http://example.org/fhir/Patient/1"},
        "b": {"reference": "urn:uuid:6f1c"},
        "c": {"reference": "#contained"},
    }]
    assert invariants.check_references_resolve(make_result(resources)) == []


def test_every_rule_is_applied_by_check():
    """A rule defined but left out of RULES would be dead code that reads as
    coverage."""
    assert len(invariants.RULES) == 7
    for rule in invariants.RULES:
        assert callable(rule)


def test_real_corpora_satisfy_every_rule():
    """The other half of the proof: the rules are strict enough to fire and
    correct enough not to fire on known-good conversions."""
    from pathlib import Path
    fixtures = sorted((Path(__file__).parent / "fixtures").glob("pcr_*.xml"))
    fixtures += sorted((Path(__file__).parent / "fixtures" / "hostile").glob("*.xml"))
    assert fixtures
    for path in fixtures:
        for result in convert(path):
            assert invariants.check(result) == [], f"{path.name} violated a rule"
