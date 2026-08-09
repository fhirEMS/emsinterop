"""FHIR-rail discharge extraction (Roadmap P6): a hospital Discharge Summary
document — a FHIR document Bundle whose Composition is LOINC 18842-5 — or any
bundle carrying the hospital Encounter + Patient, reduced to the same
transport-neutral OutcomeRecord the ADT^A03 path produces. Matching and
eOutcome write-back are shared downstream; this module is only the extractor.

Retrieval transport is deployment-specific (ITI-67/68 document query, a
hospital FHIR API, or a dropped file) and out of scope here — callers hand
this module the document JSON however it arrived.
"""

from __future__ import annotations

from .records import OutcomeRecord

DISCHARGE_SUMMARY_LOINC = "18842-5"

_ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"
#: eOutcome.01/.02 enumerate NUBC patient-discharge-status codes, so ONLY the
#: NUBC system may be passed through. The HL7 `discharge-disposition` system
#: (home/hosp/exp/…) is a different vocabulary; treating its codes as NUBC
#: would write a value the state registry's XSD rejects.
_NUBC_SYSTEMS = ("https://www.nubc.org/CodeSystem/PatDischargeStatus",)
# v3-ActCode encounter classes that are the ED visit; everything else is
# treated as inpatient for eOutcome.01-vs-.02 routing.
_EMERGENCY_CLASSES = {"EMER", "E"}


def _entries(bundle: dict, resource_type: str) -> list[dict]:
    return [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if entry.get("resource", {}).get("resourceType") == resource_type
    ]


def _resolve(bundle: dict, reference: dict | None) -> dict:
    """Follow a literal Type/id or urn:uuid reference inside the bundle."""
    ref = (reference or {}).get("reference", "")
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if not resource:
            continue
        candidates = {entry.get("fullUrl", "")}
        if resource.get("id"):
            candidates.add(f"{resource.get('resourceType')}/{resource['id']}")
            candidates.add(f"urn:uuid:{resource['id']}")
        if ref and ref in candidates:
            return resource
    return {}


def _code_in(
    concept: dict | None,
    systems: tuple[str, ...] = (),
    allow_any: bool = True,
) -> str | None:
    """Code from a CodeableConcept, preferring the named systems.

    `allow_any=False` for slots bound to a specific vocabulary: falling back to
    whatever coding happens to be first would hand a SNOMED code to a field
    that enumerates NUBC, silently corrupting the value. No code is better
    than a wrong one — the caller leaves the element nil+NV instead."""
    codings = (concept or {}).get("coding", [])
    for coding in codings:
        if coding.get("system") in systems:
            return coding.get("code")
    if not allow_any or not systems:
        return codings[0].get("code") if (codings and not systems) else None
    return codings[0].get("code") if codings else None


def is_discharge_summary(bundle: dict) -> bool:
    compositions = _entries(bundle, "Composition")
    return any(
        coding.get("code") == DISCHARGE_SUMMARY_LOINC
        for composition in compositions
        for coding in composition.get("type", {}).get("coding", [])
    )


def outcome_record_from_fhir(bundle: dict) -> OutcomeRecord:
    """Extract the eOutcome payload + matching keys from a discharge document."""
    patients = _entries(bundle, "Patient")
    encounters = _entries(bundle, "Encounter")
    if not patients or not encounters:
        raise ValueError(
            "discharge document lacks Patient/Encounter — not a usable discharge event")
    patient, encounter = patients[0], encounters[0]

    names = patient.get("name", [])
    name = next((n for n in names if n.get("use") == "official"), names[0] if names else {})

    organization = _resolve(bundle, encounter.get("serviceProvider"))
    facility = (
        organization.get("name")
        or (encounter.get("serviceProvider") or {}).get("display")
        or next((i.get("value") for i in organization.get("identifier", [])
                 if i.get("value")), "")
        or ""
    )

    encounter_class = (encounter.get("class") or {}).get("code", "").upper()
    period = encounter.get("period") or {}
    hospitalization = encounter.get("hospitalization") or {}

    diagnoses: list[str] = []
    for condition in _entries(bundle, "Condition"):
        code = _code_in(condition.get("code"), (_ICD10CM,), allow_any=False)
        if code and code not in diagnoses:
            diagnoses.append(code)

    return OutcomeRecord(
        sending_facility=facility,
        patient_class="E" if encounter_class in _EMERGENCY_CLASSES else "I",
        family_name=name.get("family", ""),
        given_name=(name.get("given") or [""])[0],
        birth_date=(patient.get("birthDate") or "").replace("-", "")[:8],
        identifiers=[i.get("value") for i in patient.get("identifier", [])
                     if i.get("value")],
        visit_number=next((i.get("value") for i in encounter.get("identifier", [])
                           if i.get("value")), ""),
        discharge_status=_code_in(hospitalization.get("dischargeDisposition"),
                                  _NUBC_SYSTEMS, allow_any=False) or "",
        admit_time=period.get("start"),
        discharge_time=period.get("end"),
        diagnoses=diagnoses,
    )
