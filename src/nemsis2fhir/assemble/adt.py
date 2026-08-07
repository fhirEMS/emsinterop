"""HL7 v2 ADT^A03 projection — the EMS encounter as the ADT visit.

The EMS call IS a visit: it begins at patient contact and ends at transfer of
care (or release/refusal on scene). This module renders that end-of-visit as
an HL7 v2.5.1 ADT^A03 from the parsed PCR — the third projection over Layer A
(FHIR mPSC, C-CDA, now v2) — so EMS encounters reach hospital ADT rails and
encounter-notification networks.

Vocabulary: PV1-36 wants NUBC/UB-04 Patient Discharge Status — the same code
set NEMSIS eOutcome.01/.02 uses natively — so the EMS disposition needs only
the small authored cm-nemsis-nubc-discharge ConceptMap, refined here by
precedence: deceased (eDisposition.19) > refusal (eDisposition.28/.30) >
transported > treated/released. DG1 carries the ICD-10-CM impressions
pass-through.

Deterministic by design (golden-corpus diffable): MSH-10 control id is a
UUIDv5 off the PCR key; MSH-7/EVN-2 default to the transfer-of-care time —
real senders pass `message_time=now`.
"""

from __future__ import annotations

from ..mapping.context import MappingContext
from ..terminology import conceptmaps

HL7_VERSION = "2.5.1"

_FIELD_ESCAPES = [("\\", "\\E\\"), ("|", "\\F\\"), ("^", "\\S\\"), ("~", "\\R\\"), ("&", "\\T\\")]

_REFUSAL_EVAL = {"4228003", "4228007"}  # evaluated-refused-care / refused evaluation
_DECEASED_ACUITY = {"4219007", "4219009"}  # dead without/with resuscitation efforts
_SEX_TO_PID8 = {"9919001": "F", "9919003": "M", "9919005": "U"}


def _esc(value: str | None) -> str:
    if not value:
        return ""
    for char, escape in _FIELD_ESCAPES:
        value = value.replace(char, escape)
    return value


def _ts(iso: str | None) -> str:
    """ISO 8601 -> HL7 DTM (YYYYMMDDHHMMSS±ZZZZ)."""
    if not iso:
        return ""
    return (
        iso.replace("-", "", 2).replace(":", "").replace("T", "")
    )


def _discharge_status(ctx: MappingContext) -> str:
    """PV1-36 with clinical precedence over the raw transport disposition."""
    acuity = ctx.pcr.value("eDisposition.19")
    if acuity in _DECEASED_ACUITY:
        return "20"  # Expired
    evaluation = ctx.pcr.value("eDisposition.28")
    transport = ctx.pcr.value("eDisposition.30")
    if evaluation in _REFUSAL_EVAL or transport == "4230009":
        return "07"  # Left against medical advice / discontinued care
    if transport:
        mapped = conceptmaps.translate("cm-nemsis-nubc-discharge", transport)
        if mapped:
            return mapped[0]["code"]
    return "01"  # treated / released


def build_adt_a03(
    ctx: MappingContext,
    receiving_application: str = "",
    receiving_facility: str = "",
    message_time: str | None = None,
) -> str:
    """The EMS encounter's end-of-visit as an ADT^A03 (ER7, \\r segments)."""
    pcr = ctx.pcr
    agency = ctx.header.value("dAgency.02") or "UNKNOWN"
    agency_name = ctx.agency_names.get(agency, "")
    end_of_visit = pcr.value("eTimes.12") or pcr.value("eTimes.11") or pcr.value("eTimes.09")
    when = _ts(message_time or end_of_visit)
    control_id = ctx.rid("adt-a03")

    msh = "|".join([
        "MSH", "^~\\&",
        _esc("nemsis2fhir"), _esc(agency_name or agency),
        _esc(receiving_application), _esc(receiving_facility),
        when, "",
        "ADT^A03^ADT_A03", control_id, "P", HL7_VERSION,
    ])

    evn = "|".join(["EVN", "A03", when, "", "", "", _ts(end_of_visit)])

    identifiers = []
    patient_id = pcr.value("ePatient.01")
    if patient_id:
        identifiers.append(f"{_esc(patient_id)}^^^{_esc(agency)}^PI")
    ssn = pcr.value("ePatient.12")
    if ssn:
        identifiers.append(f"{_esc(ssn)}^^^USA^SS")
    if not identifiers:
        identifiers.append(f"{_esc(pcr.pcr_number or 'UNKNOWN')}^^^{_esc(agency)}^PI")
    name = f"{_esc(pcr.value('ePatient.02'))}^{_esc(pcr.value('ePatient.03'))}"
    address = "^".join([
        _esc(pcr.value("ePatient.05")), "",
        _esc(pcr.value("ePatient.06")), _esc(pcr.value("ePatient.08")),
        _esc(pcr.value("ePatient.09")),
    ])
    sex_element = pcr.first("ePatient.25")
    sex = _SEX_TO_PID8.get(sex_element.value if sex_element and sex_element.has_value else "", "")
    pid = "|".join([
        "PID", "1", "", "~".join(identifiers), "", name, "",
        (pcr.value("ePatient.17") or "").replace("-", ""), sex, "", "",
        address, "", _esc(pcr.value("ePatient.18")),
    ])

    visit_number = pcr.value("eRecord.01") or "UNKNOWN"
    pv1 = "|".join([
        "PV1", "1", "E",  # the EMS encounter presents as an emergency visit
        _esc(pcr.value("eResponse.14") or pcr.value("eResponse.13") or ""),  # unit as location
        "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
        f"{_esc(visit_number)}^^^{_esc(agency)}^VN",
        "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
        _discharge_status(ctx),
        "", "", "", "", "", "", "",
        _ts(pcr.value("eTimes.07") or pcr.value("eTimes.06")),  # PV1-44 admit = patient contact
        _ts(end_of_visit),  # PV1-45 discharge = transfer of care / end of visit
    ])

    segments = [msh, evn, pid, pv1]
    set_id = 0
    for element_id in ("eSituation.11", "eSituation.12"):
        for impression in pcr.all(element_id):
            if not impression.has_value:
                continue
            set_id += 1
            kind = "F" if element_id == "eSituation.11" else "W"
            segments.append("|".join([
                "DG1", str(set_id), "",
                f"{_esc(impression.value)}^^I10",  # ICD-10-CM pass-through
                "", "", kind,
            ]))
    return "\r".join(segments) + "\r"
