"""Shared FHIR construction helpers used by the per-panel mappers."""

from __future__ import annotations

import math
import re

from ..model import NemsisElement
from ..terminology import conceptmaps, nv_pn, registry, systems

US_CORE_PROFILE_BASE = "http://hl7.org/fhir/us/core/StructureDefinition/"

_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
#: ASCII digits only — `\d` is Unicode-wide, so without [0-9] a value in
#: another numeral system would round-trip into something the source did not say.
_INT_RE = re.compile(r"^-?[0-9]+$")
#: FHIR `integer` is int32; a longer digit string is not representable.
_INT32 = (-2_147_483_648, 2_147_483_647)
#: Deliberately stricter than float(): rejects nan / inf / Infinity (valid
#: Python floats but INVALID JSON) and 1_0 (which float() silently reads as 10).
_NUMERIC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")

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


_MIDNIGHT_24 = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T24:00:00(\.\d+)?(.*)$")


def fhir_datetime(value: str | None) -> str | None:
    """A NEMSIS dateTime as a FHIR-legal one.

    `xs:dateTime` permits hour 24 to mean end-of-day, and the NEMSIS pattern
    allows it — but FHIR's dateTime regex caps hours at 23, so `24:00:00`
    passes the XSD gate and then fails every FHIR validator. Normalize it to
    00:00:00 the NEXT day, which is the same instant.

    Everything else passes through untouched: NEMSIS mandates an offset, so
    the values we see are already FHIR-shaped."""
    if not value:
        return value
    match = _MIDNIGHT_24.match(value)
    if not match:
        return value
    from datetime import date, timedelta

    year, month, day, frac, tz = match.groups()
    try:
        following = date(int(year), int(month), int(day)) + timedelta(days=1)
    except ValueError:
        return value  # not a real date; leave it for the validator to reject
    return f"{following.isoformat()}T00:00:00{frac or ''}{tz}"


def is_numeric(value: str | None) -> bool:
    """Is this NEMSIS value coercible to a FHIR Quantity value?

    Real exports carry non-numeric sentinels in numeric-looking slots — the
    XSD sanctions some (eVitals.07 'P'/'p' for a palpated BP) and dirty data
    supplies others. Callers check first and ledger the miss rather than
    letting one bad value abort the whole PCR (§8 quarantine-don't-crash)."""
    if value is None or not _NUMERIC_RE.match(value.strip()):
        return False
    try:
        # Catches overflow to inf (e.g. "1e400"), which the regex cannot see.
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def quantity(value: str, unit: str | None = None, code: str | None = None) -> dict:
    num = float(value)
    if not math.isfinite(num):
        # NaN/Infinity serialize as bare NaN/Infinity, which is invalid JSON —
        # one such value makes the ENTIRE bundle unparseable. Fail loudly here
        # rather than emit it; callers gate on is_numeric() first.
        raise ValueError(f"non-finite quantity value: {value!r}")
    q: dict = {"value": int(num) if num.is_integer() else num}
    if unit:
        q["unit"] = unit
    if code:
        q["system"] = systems.UCUM
        q["code"] = code
    return q


def unusable_value_concept(code: str = "error") -> dict:
    """dataAbsentReason for a value present in the source but not usable as a
    Quantity (non-numeric where a number is required)."""
    return {"coding": [{"system": systems.DATA_ABSENT_REASON, "code": code}]}


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
    """Data-absent-reason for a nil FHIR primitive (`_birthDate`, `_gender`,
    `_effectiveDateTime`), dual-carrying the NEMSIS original.

Uses the STANDARD FHIR `data-absent-reason` extension only — no bespoke
    extension. A custom one would force every downstream consumer to load our
    StructureDefinition before the resource validates, which is a real
    distribution burden for a translation engine whose output is meant to be
    consumed by systems we do not control.

    The NEMSIS NV/PN is mapped to its closest FHIR reason (`asked-declined`
    for Refused, `unknown` for Not Recorded, `not-applicable` for Not
    Applicable, `masked` for Not Reporting), so the source's distinction is
    preserved as far as FHIR's own vocabulary allows. Where the element has a
    CodeableConcept slot rather than a primitive — `Observation.dataAbsentReason`
    — `absent_reason_concept()` dual-codes the NEMSIS original natively; on a
    primitive there is nowhere standard to put it, so the exact source code
    lives in the conversion issue ledger.

    Handles PN as well as NV: a refused sex carries only a PN, and "the patient
    declined to state it" is clinically different from "not recorded"."""
    if element.nv:
        return {"extension": [nv_pn.data_absent_extension(element.nv)]}
    if element.pn:
        return {
            "extension": [
                {"url": systems.DATA_ABSENT_REASON_EXT,
                 "valueCode": _PN_TO_DATA_ABSENT.get(element.pn, "not-performed")}
            ]
        }
    return {
        "extension": [
            {"url": systems.DATA_ABSENT_REASON_EXT, "valueCode": "unknown"}
        ]
    }


def encounter_date(period: dict | None) -> str | None:
    """The encounter's DATE, for measurements the source left undated.

    Date precision is deliberate: it is what the source actually supports
    ("during this call"), and FHIR's variable-precision dateTime carries it
    honestly. Returns None if the encounter spans midnight — then even the date
    would be a guess — or if there is no period at all.
    """
    if not period:
        return None
    start = (period.get("start") or "")[:10]
    end = (period.get("end") or "")[:10]
    if len(start) != 10:
        return None
    if end and end != start:
        return None  # spans midnight: which day is not knowable
    return start


def can_claim_vital_signs(obs: dict) -> bool:
    """US Core vital signs (and the base vitalsigns profile) require an
    effective time precise to the day — invariant vs-1. NEMSIS groups whose
    eVitals.01 is missing or NV cannot satisfy it, so they must not claim the
    profile; the observation still carries its data, it just doesn't assert a
    conformance it would fail. Same posture as the Organization that withholds
    its US Core claim when it has no name."""
    effective = obs.get("effectiveDateTime")
    if isinstance(effective, str) and len(effective) >= 10:
        return True
    # A Period is equally conformant (the profile allows dateTime | Period) and
    # is how an undated measurement is bounded to its encounter.
    period = obs.get("effectivePeriod") or {}
    return bool(period.get("start") or period.get("end"))


def can_claim_us_core_patient(patient: dict) -> bool:
    """us-core-patient requires `gender` (min 1). A `_gender` data-absent
    extension does NOT satisfy a minimum cardinality — the validator counts
    values, not extension-only nodes — so when the source has no usable sex we
    withhold the claim rather than assert a conformance we fail. We do not
    substitute `unknown`: that asserts the sex was assessed and is not known,
    a different and stronger claim than "the patient declined to state it".
    Same posture as the Organization that withholds its claim when it has no
    name (mapping/agency.py)."""
    return isinstance(patient.get("gender"), str) and bool(patient["gender"])


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
        obs["valueDateTime"] = fhir_datetime(value)
    elif _INT_RE.match(value) and _INT32[0] <= int(value) <= _INT32[1]:
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


def address_field(key: str, value: str | None,
                  gazetteer: dict[str, str] | None = None):
    """Translate a NEMSIS geographic value into what FHIR's Address means.

    NEMSIS codes places; FHIR names them. `Address.state` is "abbreviations
    ok" and `Address.city` is "Name of city, town etc." — writing the ANSI or
    GNIS code there is displayed verbatim to a clinician as "1454997, 49".

    Returns (key, value) to emit, or None to omit. City yields None without a
    gazetteer: the code is preserved separately rather than misrepresented.
    """
    from ..terminology import geo

    if value in (None, ""):
        return None
    if key == "state":
        resolved = geo.state_abbreviation(value)
        return ("state", resolved) if resolved else None
    if key == "city":
        resolved = geo.city_name(value, gazetteer)
        return ("city", resolved) if resolved else None
    return (key, value)


def city_gnis_extension(gnis: str | None) -> dict | None:
    """Carry the GNIS feature id that `Address.city` cannot hold.

    Dropping it would breach the never-silently-drop rule, and writing it into
    `city` misrepresents a code as a name. `Address` has no coded city slot —
    `district` is the county — so the id rides in an extension and the reverse
    mapping reads it back, keeping the NEMSIS round trip exact.
    """
    from .. import conformance

    if not gnis:
        return None
    return {
        "url": conformance.canonical("StructureDefinition", "ems-city-gnis-code"),
        "valueString": str(gnis),
    }
