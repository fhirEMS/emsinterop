"""The NV/PN engine — the #1 correctness trap in NEMSIS conversion.

NV (7701xxx, on xsi:nil elements) = "no real value, and here's why"
    -> FHIR data-absent-reason. Never fabricated as a value, never skipped.
PN (8801xxx) = a clinically meaningful negative
    -> negation semantics per target resource (status=not-done + statusReason,
       negated AllergyIntolerance, negative Observation interpretation).
       The negative IS the clinical content — never dropped.

Code values are pinned from the NEMSIS 3.5.0 commonTypes_v3.xsd simple types.
"""

from __future__ import annotations

from . import systems

# --- NV: Not Values ---------------------------------------------------------

NV_NOT_APPLICABLE = "7701001"
NV_NOT_RECORDED = "7701003"
NV_NOT_REPORTING = "7701005"

NV_DISPLAY = {
    NV_NOT_APPLICABLE: "Not Applicable",
    NV_NOT_RECORDED: "Not Recorded",
    NV_NOT_REPORTING: "Not Reporting",
}

# cm-nemsis-nv: NV code -> FHIR data-absent-reason code
NV_TO_DATA_ABSENT_REASON = {
    NV_NOT_APPLICABLE: "not-applicable",
    NV_NOT_RECORDED: "unknown",
    NV_NOT_REPORTING: "masked",
}

# NV code -> CDA nullFlavor (HL7 v3 NullFlavor). CDA had first-class
# no-value semantics before FHIR: NA / UNK / MSK are exact fits.
NV_TO_NULLFLAVOR = {
    NV_NOT_APPLICABLE: "NA",
    NV_NOT_RECORDED: "UNK",
    NV_NOT_REPORTING: "MSK",
}


def nullflavor(nv_code: str | None) -> str:
    return NV_TO_NULLFLAVOR.get(nv_code or "", "UNK")

# --- PN: Pertinent Negatives ------------------------------------------------

PN_CONTRAINDICATION_NOTED = "8801001"
PN_DENIED_BY_ORDER = "8801003"
PN_EXAM_FINDING_NOT_PRESENT = "8801005"
PN_MEDICATION_ALLERGY = "8801007"
PN_MEDICATION_ALREADY_TAKEN = "8801009"
PN_NO_KNOWN_DRUG_ALLERGY = "8801013"
PN_NONE_REPORTED = "8801015"
PN_NOT_PERFORMED_BY_EMS = "8801017"
PN_REFUSED = "8801019"
PN_UNRESPONSIVE = "8801021"
PN_UNABLE_TO_COMPLETE = "8801023"
PN_NOT_IMMUNIZED = "8801025"
PN_ORDER_CRITERIA_NOT_MET = "8801027"
PN_APPROXIMATE = "8801029"
PN_SYMPTOM_NOT_PRESENT = "8801031"

PN_DISPLAY = {
    PN_CONTRAINDICATION_NOTED: "Contraindication Noted",
    PN_DENIED_BY_ORDER: "Denied By Order",
    PN_EXAM_FINDING_NOT_PRESENT: "Exam Finding Not Present",
    PN_MEDICATION_ALLERGY: "Medication Allergy",
    PN_MEDICATION_ALREADY_TAKEN: "Medication Already Taken",
    PN_NO_KNOWN_DRUG_ALLERGY: "No Known Drug Allergy",
    PN_NONE_REPORTED: "None Reported",
    PN_NOT_PERFORMED_BY_EMS: "Not Performed by EMS",
    PN_REFUSED: "Refused",
    PN_UNRESPONSIVE: "Unresponsive",
    PN_UNABLE_TO_COMPLETE: "Unable to Complete",
    PN_NOT_IMMUNIZED: "Not Immunized",
    PN_ORDER_CRITERIA_NOT_MET: "Order Criteria Not Met",
    PN_APPROXIMATE: "Approximate",
    PN_SYMPTOM_NOT_PRESENT: "Symptom Not Present",
}

# PN codes that negate the *act* (medication not given / procedure not done),
# as opposed to qualifying an observation (e.g. Approximate) or asserting a
# negative finding (NKDA, Exam Finding Not Present, Symptom Not Present).
PN_ACT_NEGATIONS = {
    PN_CONTRAINDICATION_NOTED,
    PN_DENIED_BY_ORDER,
    PN_MEDICATION_ALLERGY,
    PN_MEDICATION_ALREADY_TAKEN,
    PN_NOT_PERFORMED_BY_EMS,
    PN_REFUSED,
    PN_ORDER_CRITERIA_NOT_MET,
    PN_UNABLE_TO_COMPLETE,
}


def data_absent_extension(nv_code: str) -> dict:
    """Build the data-absent-reason extension for a value[x] element."""
    dar = NV_TO_DATA_ABSENT_REASON.get(nv_code, "unknown")
    return {"url": systems.DATA_ABSENT_REASON_EXT, "valueCode": dar}


def data_absent_code(nv_code: str) -> str:
    return NV_TO_DATA_ABSENT_REASON.get(nv_code, "unknown")


def nv_coding(nv_code: str) -> dict:
    """The original NEMSIS NV coding, retained for fidelity (dual-coding)."""
    return {
        "system": systems.NEMSIS,
        "code": nv_code,
        "display": NV_DISPLAY.get(nv_code),
    }


def pn_coding(pn_code: str) -> dict:
    return {
        "system": systems.NEMSIS,
        "code": pn_code,
        "display": PN_DISPLAY.get(pn_code),
    }


def pn_concept(pn_code: str) -> dict:
    """CodeableConcept for a PN, e.g. for statusReason on a not-done act."""
    return {"coding": [pn_coding(pn_code)], "text": PN_DISPLAY.get(pn_code)}


def section_empty_reason(nv_code: str | None) -> dict:
    """Composition.section.emptyReason (satisfies ihe-pcc-comp-1)."""
    # FHIR list-empty-reason codes: nilknown | notasked | withheld | unavailable ...
    mapping = {
        NV_NOT_APPLICABLE: "nilknown",
        NV_NOT_RECORDED: "notasked",
        NV_NOT_REPORTING: "withheld",
    }
    code = mapping.get(nv_code or "", "unavailable")
    return {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/list-empty-reason",
                "code": code,
            }
        ]
    }
