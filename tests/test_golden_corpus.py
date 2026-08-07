"""Corpus-wide invariants (every fixture) + case-specific assertions for the
cardiac-arrest and refusal/no-transport golden cases."""

import pytest

from nemsis2fhir.convert import convert
from nemsis2fhir.ingest import validate
from nemsis2fhir.issues import Disposition
from nemsis2fhir.terminology import systems

from .conftest import FIXTURES, by_type

ALL_FIXTURES = sorted(FIXTURES.glob("*.xml"))


@pytest.fixture(scope="session")
def arrest():
    return convert(FIXTURES / "pcr_cardiac_arrest.xml")[0]


@pytest.fixture(scope="session")
def refusal():
    return convert(FIXTURES / "pcr_refusal.xml")[0]


# --- corpus-wide invariants -------------------------------------------------

@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_corpus_is_xsd_valid(path):
    assert validate(path) == []


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_corpus_never_silently_drops(path):
    result = convert(path)[0]
    present = result.context.pcr.element_ids()
    flagged = {i.element_id for i in result.issues.issues}
    unaccounted = present - result.context.consumed - flagged
    assert unaccounted == set(), sorted(unaccounted)
    unmapped = result.issues.by_disposition(Disposition.UNMAPPED)
    assert unmapped == [], [i.element_id for i in unmapped]


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_corpus_mandatory_sections_complete(path):
    result = convert(path)[0]
    sections = {s["title"]: s for s in result.composition["section"]}
    for title in ("Problems", "Allergies and Intolerances", "Medication Summary"):
        assert title in sections
        assert "entry" in sections[title] or "emptyReason" in sections[title]


# --- cardiac arrest case ----------------------------------------------------

def _arrest_obs(resources, element_id):
    return [
        o for o in by_type(resources, "Observation")
        if any(c.get("code") == element_id for c in o["code"]["coding"])
    ]


def test_arrest_panel_with_values(arrest):
    gate = _arrest_obs(arrest.resources, "eArrest.01")[0]
    codes = [c["code"] for c in gate["valueCodeableConcept"]["coding"]]
    assert "3001003" in codes  # Yes, prior to EMS arrival
    assert "interpretation" not in gate  # an actual arrest is not a negative

    # Repeating eArrest.03: one Observation per resuscitation action.
    actions = _arrest_obs(arrest.resources, "eArrest.03")
    action_codes = {
        c["code"] for o in actions for c in o["valueCodeableConcept"]["coding"]
        if c["system"] == systems.NEMSIS
    }
    assert action_codes == {"3003001", "3003003", "3003005"}

    # First monitored rhythm VF; arrest onset as valueDateTime.
    rhythm = _arrest_obs(arrest.resources, "eArrest.11")[0]
    assert any(c["code"] == "3011011" for c in rhythm["valueCodeableConcept"]["coding"])
    onset = _arrest_obs(arrest.resources, "eArrest.14")[0]
    assert onset["valueDateTime"] == "2026-08-06T08:48:30-06:00"


def test_arrest_alert_communication_sent(arrest):
    communication = by_type(arrest.resources, "Communication")[0]
    assert communication["status"] == "completed"
    assert communication["sent"] == "2026-08-06T09:20:00-06:00"
    reason_codes = [c["code"] for c in communication["reasonCode"][0]["coding"]]
    assert "4224005" in reason_codes  # Yes-Cardiac Arrest


def test_arrest_gcs_three(arrest):
    gcs = [
        o for o in by_type(arrest.resources, "Observation")
        if any(c.get("code") == "9269-2" for c in o["code"]["coding"])
        and o.get("effectiveDateTime") == "2026-08-06T08:58:00-06:00"
    ]
    assert gcs and gcs[0]["valueQuantity"]["value"] == 3


def test_arrest_narrative_document(arrest):
    docs = by_type(arrest.resources, "DocumentReference")
    assert len(docs) == 1
    import base64
    text = base64.b64decode(docs[0]["content"][0]["attachment"]["data"]).decode()
    assert "defibrillated" in text
    narrative_section = [
        s for s in arrest.composition["section"] if s["title"] == "EMS Narrative"
    ]
    assert narrative_section and narrative_section[0]["entry"]


def test_arrest_valued_allergy_and_coverage(arrest):
    allergy = by_type(arrest.resources, "AllergyIntolerance")[0]
    assert allergy["code"]["coding"][0] == {"system": systems.RXNORM, "code": "7980"}
    coverage = by_type(arrest.resources, "Coverage")[0]
    assert any(c["code"] == "2601005" for c in coverage["type"]["coding"])  # Medicare
    payers = [s for s in arrest.composition["section"] if s["title"] == "Payers"]
    assert payers and payers[0]["entry"]


# --- refusal / no-transport case --------------------------------------------

def test_refusal_acts_not_done(refusal):
    admin = by_type(refusal.resources, "MedicationAdministration")[0]
    assert admin["status"] == "not-done"
    assert any(
        c["code"] == "8801019" for c in admin["statusReason"][0]["coding"]
    )  # Refused
    procedure = by_type(refusal.resources, "Procedure")[0]
    assert procedure["status"] == "not-done"
    assert any(c["code"] == "8801019" for c in procedure["statusReason"]["coding"])


def test_refusal_disposition_and_no_destination(refusal):
    encounter = by_type(refusal.resources, "Encounter")[0]
    discharge = encounter["hospitalization"]["dischargeDisposition"]["coding"]
    assert any(c["code"] == "4230009" for c in discharge)  # Patient Refused Transport
    assert "end" not in encounter.get("period", {})  # never arrived anywhere
    assert "destination" not in encounter["hospitalization"]
    location_names = {l.get("name") for l in by_type(refusal.resources, "Location")}
    assert location_names == {"EMS scene", "Medic 42"}  # no destination Location
    refusal_reason = [
        o for o in by_type(refusal.resources, "Observation")
        if any(c.get("code") == "eDisposition.31" for c in o["code"]["coding"])
    ]
    assert refusal_reason and any(
        c["code"] == "4231001"  # Against Medical Advice
        for c in refusal_reason[0]["valueCodeableConcept"]["coding"]
    )


# --- pediatric length-based case ---------------------------------------------

@pytest.fixture(scope="session")
def pediatric():
    return convert(FIXTURES / "pcr_pediatric.xml")[0]


@pytest.fixture(scope="session")
def mci():
    return convert(FIXTURES / "pcr_mci.xml")[0]


@pytest.fixture(scope="session")
def interfacility():
    return convert(FIXTURES / "pcr_interfacility.xml")[0]


def _coded(resources, code):
    return [
        o for o in by_type(resources, "Observation")
        if isinstance(o.get("code"), dict)
        and any(c.get("code") == code for c in o["code"]["coding"])
    ]


def test_pediatric_age_without_dob(pediatric):
    patient = by_type(pediatric.resources, "Patient")[0]
    assert "birthDate" not in patient
    assert patient["_birthDate"]["extension"][0]["valueCode"] == "unknown"
    age = _coded(pediatric.resources, "30525-0")[0]
    assert age["valueQuantity"] == {
        "value": 18, "unit": "months", "system": "http://unitsofmeasure.org", "code": "mo",
    }


def test_pediatric_length_based_anchors(pediatric):
    weight = _coded(pediatric.resources, "29463-7")[0]
    assert weight["valueQuantity"]["value"] == 12.5
    assert weight["valueQuantity"]["code"] == "kg"
    tape = _coded(pediatric.resources, "eExam.02")[0]
    codes = [c["code"] for c in tape["valueCodeableConcept"]["coding"]]
    assert "3502011" in codes  # Purple
    lung = _coded(pediatric.resources, "eExam.23")[0]
    assert lung["effectiveDateTime"] == "2026-08-06T18:57:00-06:00"
    assert any(c["code"] == "3523029" for c in lung["valueCodeableConcept"]["coding"])


def test_pediatric_procedure_order_criteria_not_met(pediatric):
    procedure = by_type(pediatric.resources, "Procedure")[0]
    assert procedure["status"] == "not-done"
    assert any(c["code"] == "8801027" for c in procedure["statusReason"]["coding"])


# --- MCI / triage case -------------------------------------------------------

def test_mci_triage_and_flags(mci):
    triage = _coded(mci.resources, "eScene.08")[0]
    assert any(c["code"] == "2708003" for c in triage["valueCodeableConcept"]["coding"])
    mci_flag = _coded(mci.resources, "eScene.07")[0]
    assert any(c["code"] == "9923003" for c in mci_flag["valueCodeableConcept"]["coding"])


def test_mci_prior_unit_vitals_flagged(mci):
    from nemsis2fhir.mapping.vitals import PRIOR_CARE_EXT
    group1 = [
        o for o in by_type(mci.resources, "Observation")
        if o.get("effectiveDateTime") == "2026-08-06T16:12:00-06:00"
    ]
    assert group1
    for obs in group1:
        assert any(e.get("url") == PRIOR_CARE_EXT for e in obs.get("extension", []))
    group2 = [
        o for o in by_type(mci.resources, "Observation")
        if o.get("effectiveDateTime") == "2026-08-06T16:24:00-06:00"
    ]
    assert group2
    for obs in group2:
        assert not any(e.get("url") == PRIOR_CARE_EXT for e in obs.get("extension", []))


def test_mci_injury_panel(mci):
    causes = [
        c for c in by_type(mci.resources, "Condition")
        if any(x.get("code") == "V89.2XXA" for x in c["code"].get("coding", []))
    ]
    assert causes and causes[0]["code"]["coding"][0]["system"] == systems.ICD10CM
    moi = _coded(mci.resources, "eInjury.02")[0]
    assert any(c["code"] == "2902001" for c in moi["valueCodeableConcept"]["coding"])
    alert = by_type(mci.resources, "Communication")[0]
    assert alert["status"] == "completed"
    assert any(c["code"] == "4224003" for c in alert["reasonCode"][0]["coding"])


# --- interfacility (RIPT) case -----------------------------------------------

def test_interfacility_reasons_on_encounter(interfacility):
    encounter = by_type(interfacility.resources, "Encounter")[0]
    reason_codes = [
        c["code"] for rc in encounter["reasonCode"] for c in rc.get("coding", [])
    ]
    assert "2820001" in reason_codes  # Cardiac Specialty
    texts = [rc.get("text") for rc in encounter["reasonCode"]]
    assert any(t and "catheterization" in t for t in texts)
    service_types = [
        c["code"] for t in encounter["type"] for c in t.get("coding", [])
    ]
    assert "2205005" in service_types  # Hospital-to-Hospital Transfer


def test_interfacility_prior_care_medication(interfacility):
    from nemsis2fhir.mapping.vitals import PRIOR_CARE_EXT
    heparin = by_type(interfacility.resources, "MedicationAdministration")[0]
    assert heparin["medicationCodeableConcept"]["coding"][0]["code"] == "5224"
    assert any(e.get("url") == PRIOR_CARE_EXT for e in heparin.get("extension", []))
    scene = [
        l for l in by_type(interfacility.resources, "Location")
        if l.get("name") == "Mercy Regional Medical Center"
    ]
    assert scene, "sending facility must be the scene Location"


def test_refusal_spo2_refused_but_other_vitals_present(refusal):
    observations = by_type(refusal.resources, "Observation")
    spo2 = [
        o for o in observations
        if any(c.get("code") == "59408-5" for c in o["code"]["coding"])
    ][0]
    dar = spo2["dataAbsentReason"]["coding"]
    assert any(c["code"] == "asked-declined" for c in dar)
    bp = [
        o for o in observations
        if any(c.get("code") == "85354-9" for c in o["code"]["coding"])
    ][0]
    values = {
        c["code"]["coding"][0]["code"]: c["valueQuantity"]["value"]
        for c in bp["component"]
    }
    assert values == {"8480-6": 124, "8462-4": 78}
