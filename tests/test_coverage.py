"""The never-silently-drop guarantee: every source element is consumed by a
mapper or lands in the conversion issue log — no third option."""

from pathlib import Path

from nemsis2fhir.convert import convert
from nemsis2fhir.issues import Disposition

from .conftest import CHEST_PAIN


def _flagged_ids(result):
    return {i.element_id for i in result.issues.issues}


def test_every_element_accounted_for(result):
    present = result.context.pcr.element_ids()
    unaccounted = present - result.context.consumed - _flagged_ids(result)
    assert unaccounted == set(), f"elements neither consumed nor ledgered: {sorted(unaccounted)}"


def test_golden_fixture_has_zero_unmapped(result):
    """Every panel in the golden fixture now has a mapper: the only ledger
    entries left are intentional (workbook deferrals + the dAgency.03 seed)."""
    unmapped = result.issues.by_disposition(Disposition.UNMAPPED)
    assert unmapped == [], [i.element_id for i in unmapped]
    for issue in result.issues.issues:
        assert issue.severity != "warning", issue


def test_workbook_deferrals_are_informational(result):
    issues = {i.element_id: i for i in result.issues.issues}
    outcome = issues.get("eOutcome.01")
    assert outcome is not None
    assert outcome.disposition == Disposition.DEFERRED
    assert outcome.severity == "information"
    billing = issues.get("ePayment.50")
    assert billing is not None and billing.disposition == Disposition.DEFERRED


def test_consumed_elements_are_not_flagged(result):
    flagged = _flagged_ids(result)
    for element_id in ("eVitals.06", "ePatient.25", "eMedications.03", "eHistory.06",
                       "ePatient.15", "ePatient.16", "eResponse.01"):
        assert element_id not in flagged, f"{element_id} is mapped but was flagged"


def test_issue_log_carries_no_phi(result):
    # PHI hygiene: reasons/ids only — never element values.
    for issue in result.issues.issues:
        assert "Trujillo" not in issue.reason
        assert "Cottonwood" not in issue.reason


def test_nv_allergy_is_ledgered_and_section_goes_empty(tmp_path):
    xml = CHEST_PAIN.read_text()
    # Turn the NKDA pertinent negative into an NV "not recorded".
    assert 'PN="8801013"' in xml
    mutated = xml.replace(
        '<eHistory.06 xsi:nil="true" PN="8801013"/>',
        '<eHistory.06 xsi:nil="true" NV="7701003"/>',
    )
    path = tmp_path / "nv_allergy.xml"
    path.write_text(mutated)
    result = convert(path)[0]

    logged = [i for i in result.issues.issues if i.element_id == "eHistory.06"]
    assert logged and "emptyReason" in logged[0].reason

    allergies = [r for r in result.resources if r["resourceType"] == "AllergyIntolerance"]
    assert allergies == []
    section = [s for s in result.composition["section"]
               if s["title"] == "Allergies and Intolerances"][0]
    assert "entry" not in section
    # NV 7701003 (Not Recorded) escalates to emptyReason notasked.
    assert section["emptyReason"]["coding"][0]["code"] == "notasked"
