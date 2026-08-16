"""Reverse mapping (Roadmap P6): canonical FHIR back to NEMSIS element values.

Direction discipline: the forward mapper is the spec, and reverse NEVER
invents — a value comes back only where the forward mapping is faithfully
invertible. Two sources, in priority order:

  1. the dual-coded NEMSIS original, when the CodeableConcept carries one
     (emsInterop-produced resources always do — full fidelity), and
  2. the authored ConceptMaps run in reverse (`equivalent`/`equal` rows
     only), for foreign resources coded purely in the standard systems.

Scope today: the demographics panel (Patient -> ePatient) — the round-trip
proof the rest of the panels follow. Values are returned as
{element_id: value | [values]}; the caller decides what to do with them
(registry resubmission forms, eOutcome enrichment, gap analysis).
"""

from __future__ import annotations

from ..terminology import geo, conceptmaps, systems

ADMINISTRATIVE_GENDER = "http://hl7.org/fhir/administrative-gender"


def nemsis_code_of(concept: dict | None) -> str | None:
    """The dual-coded NEMSIS original inside a CodeableConcept, if present."""
    for coding in (concept or {}).get("coding", []):
        if coding.get("system") == systems.NEMSIS:
            return coding.get("code")
    return None


def _identifier(patient: dict, system: str) -> str | None:
    for identifier in patient.get("identifier", []):
        if identifier.get("system") == system and identifier.get("value"):
            return identifier["value"]
    return None


def _omb_codings(patient: dict, extension_url: str) -> list[dict]:
    out = []
    for ext in patient.get("extension", []):
        if ext.get("url") != extension_url:
            continue
        for nested in ext.get("extension", []):
            if nested.get("url") == "ombCategory" and nested.get("valueCoding"):
                out.append(nested["valueCoding"])
    return out


def patient_to_nemsis(patient: dict) -> dict[str, str | list[str]]:
    """ePatient element values recoverable from a (US Core) Patient."""
    values: dict[str, str | list[str]] = {}

    for element_id, system in (("ePatient.01", systems.PATIENT_AGENCY_ID),
                               ("ePatient.12", systems.US_SSN)):
        value = _identifier(patient, system)
        if value:
            values[element_id] = value

    names = patient.get("name", [])
    name = next((n for n in names if n.get("use") == "official"),
                names[0] if names else {})
    if name.get("family"):
        values["ePatient.02"] = name["family"]
    given = name.get("given") or []
    if given:
        values["ePatient.03"] = given[0]
    if len(given) > 1:
        values["ePatient.04"] = given[1]

    address = (patient.get("address") or [{}])[0]
    for element_id, key in (("ePatient.05", "line"), ("ePatient.06", "city"),
                            ("ePatient.07", "district"), ("ePatient.08", "state"),
                            ("ePatient.09", "postalCode"), ("ePatient.10", "country")):
        value = address.get(key)
        if key == "line":
            value = value[0] if value else None
        if key == "state":
            # FHIR carries the USPS abbreviation; NEMSIS wants the ANSI code.
            # The map is a bijection, so the round trip is exact.
            value = geo.state_code(value)
        if key == "city":
            # The GNIS id lives in an extension, because Address.city is a
            # name and NEMSIS stores a code. Read it back from there.
            value = next(
                (e.get("valueString") for e in address.get("extension") or []
                 if str(e.get("url", "")).endswith("/ems-city-gnis-code")),
                None)
        if value:
            values[element_id] = value

    if patient.get("birthDate"):
        values["ePatient.17"] = patient["birthDate"]

    # Sex: forward mapped ePatient.25 (source of truth, ADR-007) through
    # cm-nemsis-sex; every row is equivalent, so gender reverses losslessly.
    if patient.get("gender"):
        reversed_sex = conceptmaps.reverse_translate(
            "cm-nemsis-sex", ADMINISTRATIVE_GENDER, patient["gender"], "ePatient.25")
        if reversed_sex:
            values["ePatient.25"] = reversed_sex[0]["code"]

    # Race + ethnicity both live in repeating ePatient.14; the forward mapper
    # split them across the two US Core extensions.
    race_codes: list[str] = []
    for extension_url in (systems.US_CORE_RACE_EXT, systems.US_CORE_ETHNICITY_EXT):
        for coding in _omb_codings(patient, extension_url):
            candidates = conceptmaps.reverse_translate(
                "cm-nemsis-race", coding.get("system", ""), coding.get("code", ""),
                "ePatient.14")
            race_codes.extend(c["code"] for c in candidates
                              if c["code"] not in race_codes)
    if race_codes:
        values["ePatient.14"] = race_codes

    return values
