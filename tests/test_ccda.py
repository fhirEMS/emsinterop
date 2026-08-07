"""C-CDA projection: structural conformance over the golden corpus.

Schematron-grade validation (ONC C-CDA validator) is the follow-up tier;
these tests pin the structural contract: template ids, header population,
NV -> nullFlavor, PN -> negationInd (meds, procedures, NKDA), and that both
projections (FHIR document + C-CDA) render from the same graph.
"""

from lxml import etree
import pytest

from nemsis2fhir.assemble.ccda import render_ccda
from nemsis2fhir.convert import convert

from .conftest import CHEST_PAIN, FIXTURES

NS = {"c": "urn:hl7-org:v3", "xsi": "http://www.w3.org/2001/XMLSchema-instance"}


def _render(path=CHEST_PAIN):
    result = convert(path, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    return etree.fromstring(render_ccda(result.context))


def test_header_structure():
    doc = _render()
    assert doc.tag == "{urn:hl7-org:v3}ClinicalDocument"
    templates = {t.get("root") for t in doc.findall("c:templateId", NS)}
    assert "2.16.840.1.113883.10.20.22.1.1" in templates  # US Realm Header
    assert "2.16.840.1.113883.10.20.22.1.2" in templates  # CCD
    assert doc.find("c:code", NS).get("code") == "34133-9"
    assert doc.find("c:code/c:translation", NS).get("code") == "67796-3"
    # substance-use content in the fixture -> restricted confidentiality
    assert doc.find("c:confidentialityCode", NS).get("code") == "R"
    patient = doc.find("c:recordTarget/c:patientRole/c:patient", NS)
    assert patient.find("c:name/c:family", NS).text == "Trujillo"
    assert patient.find("c:administrativeGenderCode", NS).get("code") == "F"
    assert patient.find("c:birthTime", NS).get("value") == "19800214"
    custodian = doc.find("c:custodian/c:assignedCustodian/c:representedCustodianOrganization", NS)
    assert custodian.find("c:name", NS).text == "Wasatch Valley EMS (synthetic)"
    encounter = doc.find("c:componentOf/c:encompassingEncounter", NS)
    assert encounter.find("c:effectiveTime/c:low", NS).get("value") == "20260806090445-0600"
    assert encounter.find("c:effectiveTime/c:high", NS).get("value") == "20260806094805-0600"


def test_sections_present_with_narrative():
    doc = _render()
    codes = [s.find("c:code", NS).get("code")
             for s in doc.findall(".//c:structuredBody/c:component/c:section", NS)]
    assert codes == ["11450-4", "48765-2", "10160-0", "8716-3", "47519-4"]
    for section in doc.findall(".//c:section", NS):
        assert section.find("c:text", NS) is not None


def test_problem_entries_are_icd10():
    doc = _render()
    values = doc.xpath(".//c:section[c:code/@code='11450-4']//c:observation/c:value", namespaces=NS)
    coded = [v for v in values if v.get("code")]
    assert {"I21.9", "I20.9", "I10", "E11.9"} <= {v.get("code") for v in coded}
    assert all(v.get("codeSystem") == "2.16.840.1.113883.6.90" for v in coded)


def test_nkda_is_negated_assertion():
    doc = _render()
    observations = doc.xpath(".//c:section[c:code/@code='48765-2']//c:observation", namespaces=NS)
    negated = [o for o in observations if o.get("negationInd") == "true"]
    assert len(negated) == 1
    assert negated[0].find("c:value", NS).get("code") == "416098002"


def test_pn_medication_is_negated_substance_administration():
    doc = _render()
    admins = doc.xpath(".//c:section[c:code/@code='10160-0']//c:substanceAdministration", namespaces=NS)
    assert len(admins) == 2  # aspirin given + contraindicated med
    negated = [a for a in admins if a.get("negationInd") == "true"]
    assert len(negated) == 1
    original = negated[0].find(".//c:manufacturedMaterial/c:code/c:originalText", NS)
    assert original.text == "Contraindication Noted"
    given = [a for a in admins if a.get("negationInd") is None][0]
    material = given.find(".//c:manufacturedMaterial/c:code", NS)
    assert material.get("code") == "1191"  # aspirin, RxNorm OID
    assert material.get("codeSystem") == "2.16.840.1.113883.6.88"


def test_nv_vitals_become_nullflavor():
    doc = _render()
    organizers = doc.xpath(".//c:section[c:code/@code='8716-3']//c:organizer", namespaces=NS)
    assert len(organizers) == 2  # one per VitalGroup, shared timestamps
    # group 2: SBP nil NV=7701003 -> value nullFlavor UNK
    second = organizers[1]
    sbp = [o for o in second.findall(".//c:observation", NS)
           if o.find("c:code", NS) is not None
           and o.find("c:code", NS).get("code") == "8480-6"]
    assert sbp and sbp[0].find("c:value", NS).get("nullFlavor") == "UNK"
    assert sbp[0].find("c:value", NS).get(f"{{{NS['xsi']}}}type") == "PQ"


def test_pn_procedure_negated():
    doc = _render()
    procedures = doc.xpath(".//c:section[c:code/@code='47519-4']//c:procedure", namespaces=NS)
    negated = [p for p in procedures if p.get("negationInd") == "true"]
    assert len(negated) == 1
    assert negated[0].find("c:code/c:originalText", NS).text == "Refused"


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.xml")), ids=lambda p: p.stem)
def test_corpus_renders_wellformed(path):
    doc = _render(path)
    assert doc.tag.endswith("ClinicalDocument")
    assert len(doc.findall(".//c:section", NS)) == 5
