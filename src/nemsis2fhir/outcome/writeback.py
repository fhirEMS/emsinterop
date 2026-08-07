"""eOutcome write-back: a LINKED discharge record applied to the PCR XML.

Produces the FULL corrected PCR (an updated EMSDataSet document) with the
eOutcome panel populated — the state-registry resubmission form, and the
project's first FHIR-era write in the NEMSIS direction. NUBC discharge codes
pass through unchanged (eOutcome.01/.02 speak that vocabulary natively);
ICD-10-CM diagnoses land in .10/.13. Nil+NV placeholder elements are replaced
in place, preserving XSD element order; the output re-validates against the
pinned schema in tests.

Only LINKED matches may be applied — callers enforce the review gate
(apply_outcome refuses nothing itself; it is mechanism, not policy).
"""

from __future__ import annotations

from lxml import etree

from ..ingest.parser import NEMSIS_NS, XSI_NS
from .records import OutcomeRecord

_N = "{%s}" % NEMSIS_NS
_NIL = "{%s}nil" % XSI_NS
HOSPITAL_RECEIVING = "4303005"  # eOutcome.03 External Report Type


def _set_value(parent: etree._Element, element_id: str, value: str) -> None:
    """Give a (possibly nil+NV placeholder) element a real value in place."""
    node = parent.find(f"{_N}{element_id}")
    if node is None:
        raise ValueError(f"{element_id} not present in eOutcome section")
    node.attrib.pop(_NIL, None)
    node.attrib.pop("NV", None)
    node.text = value


def _set_repeating(parent: etree._Element, element_id: str, values: list[str]) -> None:
    """Replace the placeholder occurrence(s) of a repeating element with one
    valued element per entry, at the placeholder's position (order preserved)."""
    existing = parent.findall(f"{_N}{element_id}")
    if not existing or not values:
        return
    anchor = existing[0]
    at = list(parent).index(anchor)
    for node in existing:
        parent.remove(node)
    for offset, value in enumerate(values):
        node = etree.Element(f"{_N}{element_id}")
        node.text = value
        parent.insert(at + offset, node)


def apply_outcome(pcr_xml: bytes | str, record: OutcomeRecord) -> bytes:
    """The corrected EMSDataSet with eOutcome populated from the discharge."""
    root = etree.fromstring(pcr_xml if isinstance(pcr_xml, bytes) else pcr_xml.encode())
    outcome = root.find(f".//{_N}eOutcome")
    if outcome is None:
        raise ValueError("PCR has no eOutcome section")

    is_emergency = record.patient_class == "E"
    if record.discharge_status:
        _set_value(outcome, "eOutcome.01" if is_emergency else "eOutcome.02",
                   record.discharge_status)
    if record.admit_time:
        _set_value(outcome, "eOutcome.18" if is_emergency else "eOutcome.11",
                   record.admit_time)
    if record.discharge_time and not is_emergency:
        _set_value(outcome, "eOutcome.16", record.discharge_time)
    if record.diagnoses:
        _set_repeating(outcome, "eOutcome.10" if is_emergency else "eOutcome.13",
                       record.diagnoses)

    if record.visit_number:
        # ExternalDataGroup goes between eOutcome.02 and the ED procedures
        # group per the XSD sequence.
        group = etree.Element(f"{_N}eOutcome.ExternalDataGroup")
        report_type = etree.SubElement(group, f"{_N}eOutcome.03")
        report_type.text = HOSPITAL_RECEIVING
        report_id = etree.SubElement(group, f"{_N}eOutcome.04")
        report_id.text = record.visit_number
        two = outcome.find(f"{_N}eOutcome.02")
        outcome.insert(list(outcome).index(two) + 1, group)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
