"""XSD validation + parser: NV/PN must survive parsing as first-class fields."""

from lxml import etree

from nemsis2fhir.ingest import parse, to_operation_outcome, validate


def test_fixture_is_xsd_valid(fixture_path):
    assert validate(fixture_path) == []


def test_invalid_document_quarantines_with_operation_outcome(fixture_path):
    doc = etree.parse(str(fixture_path))
    ns = "{http://www.nemsis.org}"
    # Remove a mandatory section to force a structural failure.
    for node in doc.iter(f"{ns}eDisposition"):
        node.getparent().remove(node)
    errors = validate(etree.tostring(doc))
    assert errors, "expected structural errors"
    outcome = to_operation_outcome(errors)
    assert outcome["resourceType"] == "OperationOutcome"
    assert outcome["issue"][0]["severity"] == "error"
    assert outcome["issue"][0]["code"] == "structure"


def test_parse_basics(dataset):
    assert dataset.nemsis_version == "3.5.0"
    assert len(dataset.reports) == 1
    pcr = dataset.reports[0]
    assert pcr.pcr_number == "PCR-2026-000123"
    assert pcr.uuid == "0b9160c8-52f7-45a2-9a41-51c1b6ae2f01"
    assert dataset.header.value("dAgency.02") == "4901"


def test_nv_is_first_class(dataset):
    pcr = dataset.reports[0]
    groups = pcr.groups("eVitals", "eVitals.VitalGroup")
    assert len(groups) == 2
    sbp = groups[1].first("eVitals.06")
    assert sbp.nil is True
    assert sbp.nv == "7701003"
    assert sbp.value is None
    assert not sbp.has_value
    assert sbp.is_not_value


def test_pn_is_first_class(dataset):
    pcr = dataset.reports[0]
    nkda = pcr.first("eHistory.06")
    assert nkda.nil is True
    assert nkda.pn == "8801013"
    assert nkda.is_pertinent_negative
    spo2 = pcr.groups("eVitals", "eVitals.VitalGroup")[1].first("eVitals.12")
    assert spo2.pn == "8801019"


def test_repeating_groups_and_nesting(dataset):
    pcr = dataset.reports[0]
    # eVitals.06 lives inside BloodPressureGroup; recursive lookup must find it.
    group = pcr.groups("eVitals", "eVitals.VitalGroup")[0]
    assert group.value("eVitals.06") == "142"
    meds = pcr.groups("eMedications", "eMedications.MedicationGroup")
    assert len(meds) == 2
    crews = pcr.groups("eCrew", "eCrew.CrewGroup")
    assert [g.value("eCrew.01") for g in crews] == ["P123", "E456"]


def test_phone_attribute_preserved(dataset):
    phone = dataset.reports[0].first("ePatient.18")
    assert phone.attributes.get("PhoneNumberType") == "9913009"
