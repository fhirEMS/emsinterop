"""Reverse mapping (P6): ConceptMaps run backwards + the Patient -> ePatient
round-trip proof. Reverse never invents: only equivalent/equal rows reverse,
and only forward-mapped values come back."""

import pytest

from emsinterop.convert import convert
from emsinterop.ingest import parse
from emsinterop.mapping.reverse import nemsis_code_of, patient_to_nemsis
from emsinterop.terminology import conceptmaps, systems

from .conftest import FIXTURES

ADMINISTRATIVE_GENDER = "http://hl7.org/fhir/administrative-gender"


def test_reverse_translate_equivalent_rows():
    reversed_sex = conceptmaps.reverse_translate(
        "cm-nemsis-sex", ADMINISTRATIVE_GENDER, "female", "ePatient.25")
    assert [c["code"] for c in reversed_sex] == ["9919001"]
    assert reversed_sex[0]["system"] == systems.NEMSIS
    assert reversed_sex[0]["display"] == "Female"


def test_reverse_translate_refuses_wider_rows():
    """cm-nemsis-priority maps several NEMSIS codes to v3-ActPriority with
    equivalence=wider — reversing those would fabricate precision, so wider
    rows must not appear in the reverse index."""
    forward_wider = {
        (group.get("target"), target["code"])
        for group in conceptmaps.load("cm-nemsis-priority")["group"]
        for element in group["element"]
        for target in element.get("target", [])
        if target.get("equivalence") == "wider"
    }
    assert forward_wider, "fixture assumption: priority map has wider rows"
    for target_system, code in forward_wider:
        candidates = conceptmaps.reverse_translate(
            "cm-nemsis-priority", target_system, code)
        equivalent_sources = conceptmaps._reverse_index("cm-nemsis-priority").get(
            (target_system, code), [])
        assert [c["code"] for c in candidates] == equivalent_sources


def test_reverse_translate_unknown_is_empty():
    assert conceptmaps.reverse_translate(
        "cm-nemsis-sex", ADMINISTRATIVE_GENDER, "other") == []


def test_nemsis_code_of_dual_coded_concept():
    concept = {"coding": [
        {"system": "http://snomed.info/sct", "code": "26643006"},
        {"system": systems.NEMSIS, "code": "9927025"},
    ]}
    assert nemsis_code_of(concept) == "9927025"
    assert nemsis_code_of({"coding": [{"system": "http://loinc.org", "code": "x"}]}) is None
    assert nemsis_code_of(None) is None


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("pcr_*.xml")),
                         ids=lambda p: p.stem)
def test_patient_round_trip(fixture):
    """convert() then reverse: every recoverable ePatient value equals the
    source PCR's — the P6 round-trip guarantee for demographics."""
    result = convert(fixture)[0]
    patients = [r for r in result.resources if r["resourceType"] == "Patient"]
    if not patients:
        pytest.skip("fixture has no Patient resource")
    values = patient_to_nemsis(patients[0])
    pcr = parse(fixture).reports[0]

    for element_id in ("ePatient.01", "ePatient.02", "ePatient.03", "ePatient.05",
                       "ePatient.06", "ePatient.07", "ePatient.08", "ePatient.09",
                       "ePatient.10", "ePatient.12", "ePatient.17", "ePatient.25"):
        source = pcr.value(element_id)
        if source:
            assert values.get(element_id) == source, element_id

    # Repeating race/ethnicity: every source code with a CDC target must come
    # back; order-insensitive (race and ethnicity ride separate extensions).
    reversible = {
        el.value for el in pcr.all("ePatient.14")
        if el.has_value and conceptmaps.translate(
            "cm-nemsis-race", el.value, systems.CDC_RACE_ETHNICITY)
    }
    assert set(values.get("ePatient.14", [])) == reversible
