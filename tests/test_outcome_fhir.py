"""The FHIR half of the inbound outcome loop: a hospital Discharge Summary
document (LOINC 18842-5) reduces to the same OutcomeRecord as the ADT^A03
rail and rides the shared match + eOutcome write-back."""

import json

from emsinterop.ingest import parse, validate
from emsinterop.outcome import (
    MatchVerdict,
    apply_outcome,
    is_discharge_summary,
    outcome_record,
    outcome_record_from_fhir,
    parse_adt,
    score_match,
)

from .conftest import CHEST_PAIN, FIXTURES

DISCHARGE_DOC = FIXTURES / "fhir" / "discharge_chest_pain.json"
ADT_DISCHARGE = FIXTURES / "hl7v2" / "discharge_chest_pain.hl7"


def _bundle():
    return json.loads(DISCHARGE_DOC.read_text())


def test_is_discharge_summary():
    assert is_discharge_summary(_bundle())
    assert not is_discharge_summary({"resourceType": "Bundle", "entry": []})


def test_extraction_matches_the_adt_rail():
    """Same discharge event, two transports → equivalent OutcomeRecords
    (facility naming differs by what each rail carries: MSH-4 code vs
    Organization name — both must satisfy the facility signal)."""
    fhir = outcome_record_from_fhir(_bundle())
    adt = outcome_record(parse_adt(ADT_DISCHARGE.read_text()))

    assert fhir.patient_class == adt.patient_class == "E"
    assert (fhir.family_name, fhir.given_name) == (adt.family_name, adt.given_name)
    assert fhir.birth_date == adt.birth_date == "19800214"
    assert fhir.visit_number == adt.visit_number == "V20260806-042"
    assert fhir.discharge_status == adt.discharge_status == "09"
    assert fhir.diagnoses == adt.diagnoses == ["I21.4", "I10"]
    assert fhir.admit_time == "2026-08-06T09:52:12-06:00"
    assert fhir.discharge_time == "2026-08-07T03:00:00-06:00"
    assert fhir.sending_facility == "Salt Lake General Hospital"
    assert "MRN778812" in fhir.identifiers


def test_document_links_to_the_pcr():
    record = outcome_record_from_fhir(_bundle())
    pcr = parse(CHEST_PAIN).reports[0]
    result = score_match(pcr, record)
    assert result.verdict is MatchVerdict.LINKED
    assert result.signals == {"identity": True, "timing": True, "facility": True}


def test_wrong_facility_never_links():
    bundle = _bundle()
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if resource["resourceType"] == "Organization":
            resource["name"] = "Mountain West Medical Center"
            resource["identifier"] = []
    record = outcome_record_from_fhir(bundle)
    result = score_match(parse(CHEST_PAIN).reports[0], record)
    assert result.verdict is not MatchVerdict.LINKED
    assert result.signals["facility"] is False


def test_writeback_from_document_is_xsd_valid():
    record = outcome_record_from_fhir(_bundle())
    corrected = apply_outcome(CHEST_PAIN.read_bytes(), record)
    assert validate(corrected) == []

    pcr = parse(corrected).reports[0]
    # ED-class discharge → eOutcome.01 + ED diagnoses/times (mirrors the rail
    # contract in writeback.py).
    assert pcr.value("eOutcome.01") == "09"
    assert pcr.value("eOutcome.18") == "2026-08-06T09:52:12-06:00"
    assert pcr.value("eOutcome.04") == "V20260806-042"


def test_missing_encounter_is_rejected():
    bundle = {"resourceType": "Bundle", "entry": [
        {"resource": {"resourceType": "Patient", "id": "p"}}]}
    try:
        outcome_record_from_fhir(bundle)
    except ValueError as error:
        assert "Patient/Encounter" in str(error)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for missing Encounter")
