"""Conditions, allergies (NKDA!), symptoms with pertinent negatives, DS4P."""

from nemsis2fhir.terminology import systems

from .conftest import by_type


def test_primary_impression_condition(resources):
    conditions = by_type(resources, "Condition")
    icd = [
        c
        for c in conditions
        if any(x.get("system") == systems.ICD10CM for x in c["code"].get("coding", []))
    ]
    codes = {x["code"] for c in icd for x in c["code"]["coding"]}
    assert {"I21.9", "I20.9", "I10", "E11.9"} <= codes
    primary = [
        c for c in icd if any(x["code"] == "I21.9" for x in c["code"]["coding"])
    ][0]
    assert primary["onsetDateTime"] == "2026-08-06T08:30:00-06:00"
    assert primary["category"][0]["coding"][0]["code"] == "encounter-diagnosis"


def test_chief_complaint_free_text(resources):
    conditions = by_type(resources, "Condition")
    chief = [c for c in conditions if c["code"].get("text", "").startswith("Crushing")]
    assert chief


def test_nkda_negated_allergy(resources):
    allergies = by_type(resources, "AllergyIntolerance")
    assert len(allergies) == 1
    nkda = allergies[0]
    codes = [(c["system"], c["code"]) for c in nkda["code"]["coding"]]
    assert (systems.SNOMED, "409137002") in codes  # No known drug allergy
    assert (systems.NEMSIS, "8801013") in codes  # original PN retained
    assert nkda["category"] == ["medication"]


def test_symptom_pertinent_negative(resources):
    observations = by_type(resources, "Observation")
    negatives = [
        o
        for o in observations
        if any(c.get("code") == "NEG" for i in o.get("interpretation", []) for c in i["coding"])
    ]
    assert negatives, "PN SymptomNotPresent must yield a negative-interpretation Observation"


def test_home_medication_statement(resources):
    statements = by_type(resources, "MedicationStatement")
    assert len(statements) == 1
    assert statements[0]["medicationCodeableConcept"]["coding"][0] == {
        "system": systems.RXNORM,
        "code": "17767",
    }


def test_ds4p_tagging_on_substance_use(resources):
    observations = by_type(resources, "Observation")
    substance = [
        o
        for o in observations
        if any(c.get("code") == "eHistory.17" for c in o["code"]["coding"])
    ]
    assert substance
    labels = {c["code"] for c in substance[0]["meta"]["security"]}
    assert {"R", "ETH"} <= labels
