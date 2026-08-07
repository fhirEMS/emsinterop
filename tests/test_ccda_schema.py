"""C-CDA schema tier: every corpus render validates against the CDA R2 XSD.

Env-gated like the other oracle tiers: set NEMSIS2FHIR_CCDA_SCHEMA=1 to run.
The normative CDA R2 core schema is vendored in schemas/cda/ (HL7 BSD-style
license permits redistribution — see schemas/cda/README.md), so this tier is
fully offline. XSD checks structure, ordering, and datatype lexical rules;
template conformance (C-CDA/ONC schematron) remains the follow-up tier.
"""

import os
from pathlib import Path

import pytest
from lxml import etree

from nemsis2fhir.assemble.ccda import render_ccda
from nemsis2fhir.convert import convert

from .conftest import FIXTURES

pytestmark = pytest.mark.skipif(
    os.environ.get("NEMSIS2FHIR_CCDA_SCHEMA") != "1",
    reason="set NEMSIS2FHIR_CCDA_SCHEMA=1 to run the CDA schema tier",
)

CDA_XSD = (
    Path(__file__).resolve().parents[1]
    / "schemas" / "cda" / "infrastructure" / "cda" / "CDA.xsd"
)
NS = {"c": "urn:hl7-org:v3"}


@pytest.fixture(scope="module")
def cda_schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(CDA_XSD)))


def _render(path) -> etree._Element:
    result = convert(str(path), agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    return etree.fromstring(render_ccda(result.context))


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.xml")), ids=lambda p: p.stem)
def test_corpus_validates_against_cda_schema(cda_schema, path):
    doc = _render(path)
    assert cda_schema.validate(doc), "\n".join(
        str(e) for e in cda_schema.error_log
    )


def test_schema_is_not_vacuous(cda_schema):
    """Negative controls: the tier must actually bite. A misordered header,
    a malformed TS, and a missing required consumable must each fail."""
    doc = _render(FIXTURES / "pcr_chest_pain.xml")
    effective = doc.find("c:effectiveTime", NS)
    doc.remove(effective)
    doc.insert(2, effective)  # effectiveTime before code: sequence violation
    assert not cda_schema.validate(doc)

    doc = _render(FIXTURES / "pcr_chest_pain.xml")
    doc.find("c:effectiveTime", NS).set("value", "2026-08-06")  # not a CDA TS
    assert not cda_schema.validate(doc)

    doc = _render(FIXTURES / "pcr_chest_pain.xml")
    substance = doc.find(".//c:substanceAdministration", NS)
    substance.remove(substance.find("c:consumable", NS))  # required element
    assert not cda_schema.validate(doc)
