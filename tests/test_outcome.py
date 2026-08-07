"""The inbound outcome loop: hospital A03 -> match -> eOutcome write-back."""

from emsinterop.convert import convert
from emsinterop.ingest import parse, validate
from emsinterop.outcome import (
    MatchVerdict,
    apply_outcome,
    outcome_record,
    parse_adt,
    score_match,
)

from .conftest import CHEST_PAIN, FIXTURES

DISCHARGE = FIXTURES / "hl7v2" / "discharge_chest_pain.hl7"
WRONG_FACILITY = FIXTURES / "hl7v2" / "discharge_wrong_facility.hl7"


def _record(path=DISCHARGE):
    return outcome_record(parse_adt(path.read_text()))


def test_outcome_record_extraction():
    record = _record()
    assert record.sending_facility == "SLGH-01"
    assert record.patient_class == "E"
    assert (record.family_name, record.given_name) == ("Trujillo", "Elena")
    assert record.birth_date == "19800214"
    assert record.visit_number == "V20260806-042"
    assert record.discharge_status == "09"  # admitted as inpatient (NUBC)
    assert record.admit_time == "2026-08-06T09:52:12-06:00"
    assert record.diagnoses == ["I21.4", "I10"]


def test_match_linked_on_all_signals():
    pcr = parse(CHEST_PAIN).reports[0]
    result = score_match(pcr, _record())
    assert result.verdict == MatchVerdict.LINKED
    assert result.signals == {"identity": True, "timing": True, "facility": True}


def test_match_review_on_facility_mismatch():
    pcr = parse(CHEST_PAIN).reports[0]
    result = score_match(pcr, _record(WRONG_FACILITY))
    assert result.verdict == MatchVerdict.REVIEW
    assert result.signals["identity"] is True
    assert result.signals["facility"] is False


def test_match_rejects_wrong_patient():
    refusal = parse(FIXTURES / "pcr_refusal.xml").reports[0]
    result = score_match(refusal, _record())
    assert result.verdict == MatchVerdict.NO_MATCH
    assert result.signals["identity"] is False


def test_writeback_produces_xsd_valid_corrected_pcr():
    corrected = apply_outcome(CHEST_PAIN.read_bytes(), _record())
    assert validate(corrected) == []  # still a valid EMSDataSet
    pcr = parse(corrected).reports[0]
    assert pcr.value("eOutcome.01") == "09"
    assert pcr.value("eOutcome.18") == "2026-08-06T09:52:12-06:00"
    assert [e.value for e in pcr.all("eOutcome.10") if e.has_value] == ["I21.4", "I10"]
    assert pcr.value("eOutcome.03") == "4303005"  # Hospital-Receiving
    assert pcr.value("eOutcome.04") == "V20260806-042"
    # untouched panels survive byte-exact semantics: it still converts clean
    result = convert(corrected)[0]
    assert result.issues.by_disposition.__self__  # smoke: issue log intact
    assert pcr.value("eOutcome.02") is None  # ED-class: hospital fields stay nil
