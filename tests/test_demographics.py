"""DEMDataSet ingest: the agency roster that completes the Organization.

The EMSDataSet header has no dAgency.03 (agency name); US Core Organization
requires one. These tests prove the DEMDataSet path supplies it end-to-end:
XSD-valid roster -> agency_names() -> convert(agency_names=...) -> Organization
with a name and the us-core-organization claim (mapping/agency.py stops
seeding the dAgency.03 gap).
"""

from pathlib import Path

from lxml import etree

from emsinterop.convert import convert
from emsinterop.ingest import (
    agency_names,
    facility_names,
    to_operation_outcome,
    validate_dem,
)

from .conftest import by_type

# In fixtures/dem/ (not fixtures/) so the EMSDataSet corpus globs
# (tests/*.py, scripts/tier2-validate.sh: fixtures/*.xml) never pick it up.
DEM_FIXTURE = Path(__file__).parent / "fixtures" / "dem" / "dem_agency.xml"

AGENCY_NAME = "Wasatch Valley EMS (synthetic)"


def test_dem_fixture_is_xsd_valid():
    assert validate_dem(DEM_FIXTURE) == []


def test_invalid_dem_document_reports_operation_outcome():
    doc = etree.parse(str(DEM_FIXTURE))
    ns = "{http://www.nemsis.org}"
    # Remove the mandatory dConfiguration section to force a structural failure.
    for node in doc.iter(f"{ns}dConfiguration"):
        node.getparent().remove(node)
    errors = validate_dem(etree.tostring(doc))
    assert errors, "expected structural errors"
    outcome = to_operation_outcome(errors)
    assert outcome["resourceType"] == "OperationOutcome"
    assert outcome["issue"][0]["severity"] == "error"
    assert outcome["issue"][0]["code"] == "structure"


def test_agency_names_keys_both_identifiers():
    names = agency_names(DEM_FIXTURE)
    # Both dAgency.01 (state id) and dAgency.02 (number) key the dAgency.03 name.
    assert names == {"UT-4901": AGENCY_NAME, "4901": AGENCY_NAME}


def test_nil_agency_name_yields_no_entry():
    doc = etree.parse(str(DEM_FIXTURE))
    ns = "{http://www.nemsis.org}"
    xsi = "{http://www.w3.org/2001/XMLSchema-instance}"
    for node in doc.iter(f"{ns}dAgency.03"):
        node.text = None
        node.set(f"{xsi}nil", "true")
        node.set("NV", "7701003")
    assert agency_names(etree.tostring(doc)) == {}


def test_facility_names():
    assert facility_names(DEM_FIXTURE) == {
        "UT-HOSP-100": "Wasatch Valley Medical Center (synthetic)"
    }


def test_convert_with_dem_roster_completes_us_core_organization(fixture_path):
    result = convert(fixture_path, agency_names=agency_names(DEM_FIXTURE))[0]
    orgs = [
        org
        for org in by_type(result.resources, "Organization")
        if any(i.get("value") == "4901" for i in org.get("identifier", []))
    ]
    assert len(orgs) == 1
    org = orgs[0]
    assert org["name"] == AGENCY_NAME
    assert "_name" not in org
    assert any(
        "us-core-organization" in profile
        for profile in org.get("meta", {}).get("profile", [])
    )
    # The dAgency.03 seeded-gap issue is no longer logged once the name arrives.
    assert not any(i.element_id == "dAgency.03" for i in result.issues.issues)
