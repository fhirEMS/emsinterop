"""MedicationAdministration / Procedure incl. the PN act-negation rule."""

from nemsis2fhir.terminology import systems

from .conftest import by_type


def test_aspirin_administration(resources):
    admins = by_type(resources, "MedicationAdministration")
    given = [a for a in admins if a["status"] == "completed"]
    assert len(given) == 1
    aspirin = given[0]
    assert aspirin["medicationCodeableConcept"]["coding"][0] == {
        "system": systems.RXNORM,
        "code": "1191",
    }
    assert aspirin["effectiveDateTime"] == "2026-08-06T09:10:00-06:00"
    route_codes = [(c["system"], c["code"]) for c in aspirin["dosage"]["route"]["coding"]]
    assert (systems.SNOMED, "26643006") in route_codes  # oral, via cm-nemsis-medroute
    assert (systems.NEMSIS, "9927035") in route_codes
    assert aspirin["dosage"]["dose"]["value"] == 324
    assert aspirin["dosage"]["dose"]["unit"] == "Milligrams (mg)"
    performer = aspirin["performer"][0]
    assert performer["actor"]["reference"].startswith("Practitioner/")
    function_codes = [c["code"] for c in performer["function"]["coding"]]
    assert "9905007" in function_codes  # Paramedic


def test_pn_medication_not_done(resources):
    admins = by_type(resources, "MedicationAdministration")
    withheld = [a for a in admins if a["status"] == "not-done"]
    assert len(withheld) == 1
    admin = withheld[0]
    reason = admin["statusReason"][0]["coding"]
    assert any(c["system"] == systems.NEMSIS and c["code"] == "8801001" for c in reason)
    assert "dosage" not in admin  # a not-given med must not carry a dose


def test_medication_performer_resolves_shared_practitioner(resources):
    admins = [a for a in by_type(resources, "MedicationAdministration") if a["status"] == "completed"]
    practitioner_ref = admins[0]["performer"][0]["actor"]["reference"]
    practitioner_id = practitioner_ref.split("/")[1]
    practitioners = by_type(resources, "Practitioner")
    match = [p for p in practitioners if p["id"] == practitioner_id]
    assert match and match[0]["identifier"][0]["value"] == "P123"


def test_ecg_procedure(resources):
    procedures = by_type(resources, "Procedure")
    done = [p for p in procedures if p["status"] == "completed"]
    assert len(done) == 1
    ecg = done[0]
    assert ecg["code"]["coding"][0] == {"system": systems.SNOMED, "code": "268400002"}
    assert ecg["performedDateTime"] == "2026-08-06T09:12:00-06:00"
    outcome_codes = [c["code"] for c in ecg["outcome"]["coding"]]
    assert "9923003" in outcome_codes  # Successful (Yes)
    complication_codes = [
        c["code"] for concept in ecg["complication"] for c in concept["coding"]
    ]
    assert "3907033" in complication_codes  # None (recorded, not dropped)


def test_pn_procedure_not_done(resources):
    procedures = by_type(resources, "Procedure")
    refused = [p for p in procedures if p["status"] == "not-done"]
    assert len(refused) == 1
    reason = refused[0]["statusReason"]["coding"]
    assert any(c["system"] == systems.NEMSIS and c["code"] == "8801019" for c in reason)


def test_attempts_and_response_observations(resources):
    observations = by_type(resources, "Observation")
    attempts = [
        o
        for o in observations
        if any(c.get("code") == "eProcedures.05" for c in o["code"]["coding"])
    ]
    assert attempts and attempts[0]["valueInteger"] == 1
    assert attempts[0]["partOf"][0]["reference"].startswith("Procedure/")
