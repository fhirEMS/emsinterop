"""Shared FHIR construction helpers used by the per-panel mappers."""

from __future__ import annotations

import re

from ..model import NemsisElement
from ..terminology import conceptmaps, nv_pn, registry, systems

US_CORE_PROFILE_BASE = "http://hl7.org/fhir/us/core/StructureDefinition/"

_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_INT_RE = re.compile(r"^-?\d+$")

YES = "9923003"  # ItemsYesNo: Yes
NO = "9923001"  # ItemsYesNo: No

# Observation PN semantics: negatives that assert a finding-was-checked-and-absent
_PN_NEGATIVE_FINDINGS = {
    nv_pn.PN_EXAM_FINDING_NOT_PRESENT,
    nv_pn.PN_SYMPTOM_NOT_PRESENT,
}
# ...vs negatives that explain why no value could be obtained
_PN_TO_DATA_ABSENT = {
    nv_pn.PN_REFUSED: "asked-declined",
    nv_pn.PN_UNABLE_TO_COMPLETE: "not-performed",
    nv_pn.PN_UNRESPONSIVE: "not-performed",
}

V3_INTERPRETATION = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"


def identifier(system: str, value: str) -> dict:
    return {"system": system, "value": value}


def quantity(value: str, unit: str | None = None, code: str | None = None) -> dict:
    num = float(value)
    q: dict = {"value": int(num) if num.is_integer() else num}
    if unit:
        q["unit"] = unit
    if code:
        q["system"] = systems.UCUM
        q["code"] = code
    return q


def loinc(code: str, display: str | None = None) -> dict:
    coding: dict = {"system": systems.LOINC, "code": code}
    if display:
        coding["display"] = display
    return {"coding": [coding], "text": display} if display else {"coding": [coding]}


def element_concept(element: NemsisElement) -> dict | None:
    """CodeableConcept from a coded NEMSIS element's own code registry entry."""
    if not element.has_value:
        return None
    return {
        "coding": [registry.nemsis_coding(element.element_id, element.value)],
        "text": registry.display(element.element_id, element.value),
    }


def absent_reason_concept(element: NemsisElement) -> dict:
    """Observation.dataAbsentReason (or similar CodeableConcept slot) for an
    element carrying NV or a no-value PN. Dual-coded: FHIR DAR + NEMSIS code."""
    codings: list[dict] = []
    text = None
    if element.nv:
        codings.append(
            {
                "system": systems.DATA_ABSENT_REASON,
                "code": nv_pn.data_absent_code(element.nv),
            }
        )
        codings.append(nv_pn.nv_coding(element.nv))
        text = nv_pn.NV_DISPLAY.get(element.nv)
    elif element.pn:
        codings.append(
            {
                "system": systems.DATA_ABSENT_REASON,
                "code": _PN_TO_DATA_ABSENT.get(element.pn, "not-performed"),
            }
        )
        codings.append(nv_pn.pn_coding(element.pn))
        text = nv_pn.PN_DISPLAY.get(element.pn)
    else:
        codings.append({"system": systems.DATA_ABSENT_REASON, "code": "unknown"})
    concept: dict = {"coding": codings}
    if text:
        concept["text"] = text
    return concept


def is_negative_finding(element: NemsisElement) -> bool:
    return element.pn in _PN_NEGATIVE_FINDINGS


def negative_interpretation() -> list[dict]:
    return [{"coding": [{"system": V3_INTERPRETATION, "code": "NEG", "display": "Negative"}]}]


def primitive_absent_extension(element: NemsisElement) -> dict:
    """data-absent-reason extension for a nil FHIR primitive (e.g. _birthDate)."""
    return {"extension": [nv_pn.data_absent_extension(element.nv or "")]}


def claim_profiles(resource: dict, *profile_names: str) -> dict:
    """Assert US Core profile conformance claims in meta.profile."""
    meta = resource.setdefault("meta", {})
    profiles = meta.setdefault("profile", [])
    for name in profile_names:
        url = US_CORE_PROFILE_BASE + name
        if url not in profiles:
            profiles.append(url)
    return resource


def apply_smart_value(obs: dict, element: NemsisElement) -> None:
    """Set the best-typed Observation.value[x] for a NEMSIS element: coded
    elements get a dual-coded CodeableConcept, ISO timestamps valueDateTime,
    integers valueInteger, anything else valueString."""
    value = element.value or ""
    if registry.is_known(element.element_id, value):
        obs["valueCodeableConcept"] = conceptmaps.dual_code(element.element_id, value)
    elif _DATETIME_RE.match(value):
        obs["valueDateTime"] = value
    elif _INT_RE.match(value):
        obs["valueInteger"] = int(value)
    else:
        obs["valueString"] = value


def course_observation(
    ctx,
    element: NemsisElement,
    discriminator: str,
    category: str = "survey",
) -> dict | None:
    """Generic operational/EMS-course Observation for a valued NEMSIS element
    (delays, dispositions, protocols, scene facts). Callers handle NV/PN cases;
    a value-less element yields None."""
    if not element.has_value:
        return None
    obs: dict = {
        "resourceType": "Observation",
        "id": ctx.rid("Observation", discriminator),
        "status": "final",
        "category": [
            {"coding": [{"system": systems.OBSERVATION_CATEGORY, "code": category}]}
        ],
        "code": {
            "coding": [{"system": systems.NEMSIS, "code": element.element_id}],
            "text": registry.element_name(element.element_id) or element.element_id,
        },
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
    }
    apply_smart_value(obs, element)
    return ctx.add(obs)
