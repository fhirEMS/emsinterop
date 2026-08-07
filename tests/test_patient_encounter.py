"""Patient (ADR-006/007) and the Encounter spine (ADR-004)."""

from emsinterop.terminology import systems

from .conftest import by_type


def _patient(resources):
    return by_type(resources, "Patient")[0]


def _encounter(resources):
    return by_type(resources, "Encounter")[0]


def test_sex_from_epatient25(resources):
    patient = _patient(resources)
    assert patient["gender"] == "female"
    birthsex = [
        e for e in patient.get("extension", []) if e["url"] == systems.US_CORE_BIRTHSEX_EXT
    ]
    assert birthsex and birthsex[0]["valueCode"] == "F"


def test_race_dual_carry(resources):
    patient = _patient(resources)
    race = [e for e in patient["extension"] if e["url"] == systems.US_CORE_RACE_EXT]
    assert race, "us-core-race extension missing"
    omb = [x for x in race[0]["extension"] if x["url"] == "ombCategory"]
    assert omb[0]["valueCoding"]["code"] == "2106-3"  # White
    # NEMSIS lists Hispanic-or-Latino under race; it must land in ETHNICITY.
    ethnicity = [e for e in patient["extension"] if e["url"] == systems.US_CORE_ETHNICITY_EXT]
    assert ethnicity
    omb_eth = [x for x in ethnicity[0]["extension"] if x["url"] == "ombCategory"]
    assert omb_eth[0]["valueCoding"]["code"] == "2135-2"


def test_patient_identity_never_fabricates_mrn(resources):
    patient = _patient(resources)
    systems_used = {i["system"] for i in patient["identifier"]}
    assert systems.PATIENT_AGENCY_ID in systems_used
    temp = [i for i in patient["identifier"] if i.get("use") == "temp"]
    assert temp and temp[0]["value"] == "PCR-2026-000123"
    assert patient["birthDate"] == "1980-02-14"
    assert patient["name"][0]["family"] == "Trujillo"


def test_encounter_spine(resources):
    encounter = _encounter(resources)
    assert encounter["status"] == "finished"
    assert encounter["class"]["code"] == "FLD"
    assert encounter["period"]["start"] == "2026-08-06T09:04:45-06:00"  # eTimes.06
    assert encounter["period"]["end"] == "2026-08-06T09:48:05-06:00"  # eTimes.12
    identifier_systems = {i["system"] for i in encounter["identifier"]}
    assert systems.INCIDENT_ID in identifier_systems
    assert systems.RESPONSE_ID in identifier_systems
    # priority: 2223001 Emergent -> v3 ActPriority EM, dual-coded
    codes = [(c["system"], c["code"]) for c in encounter["priority"]["coding"]]
    assert (systems.V3_ACT_PRIORITY, "EM") in codes
    assert (systems.NEMSIS, "2223001") in codes
    assert encounter["serviceProvider"]["reference"].startswith("Organization/")


def test_everything_references_the_encounter(resources):
    encounter_ref = f"Encounter/{_encounter(resources)['id']}"
    for resource in resources:
        if resource["resourceType"] in ("Observation", "Procedure"):
            assert resource["encounter"]["reference"] == encounter_ref
        elif resource["resourceType"] == "MedicationAdministration":
            assert resource["context"]["reference"] == encounter_ref


def test_scene_location_with_gps(resources):
    locations = by_type(resources, "Location")
    scene = [l for l in locations if l.get("name") == "EMS scene"]
    assert scene
    assert abs(scene[0]["position"]["latitude"] - 40.762807) < 1e-6
    destination = [l for l in locations if l.get("name") == "Salt Lake General Hospital"]
    assert destination
    encounter = _encounter(resources)
    assert encounter["hospitalization"]["destination"]["reference"] == (
        f"Location/{destination[0]['id']}"
    )
    # transport disposition dual-coded on dischargeDisposition
    discharge = encounter["hospitalization"]["dischargeDisposition"]["coding"]
    assert any(c["code"] == "4230001" for c in discharge)


def test_crew_practitioners(resources):
    practitioners = by_type(resources, "Practitioner")
    ids = {p["identifier"][0]["value"] for p in practitioners}
    assert ids == {"P123", "E456"}
    roles = by_type(resources, "PractitionerRole")
    assert len(roles) == 2
    level_codes = [
        c["code"]
        for role in roles
        for concept in role.get("code", [])
        for c in concept["coding"]
    ]
    assert "9925007" in level_codes  # Paramedic
