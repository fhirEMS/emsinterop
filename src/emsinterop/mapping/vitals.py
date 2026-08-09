"""eVitals -> Observations (US Core Vital Signs).

Repeating-group rule (Architecture §4.3): each VitalGroup emits one Observation
per measured element present, ALL sharing effectiveDateTime = eVitals.01. NV ->
Observation.dataAbsentReason; PN Refused/Unable -> dataAbsentReason with the
PN retained; PN ExamFindingNotPresent -> negative interpretation. GCS total is
aggregated/validated by a typed helper (ADR-002).
"""

from __future__ import annotations

from ..issues import Disposition
from ..model import NemsisElement, NemsisGroup
from ..terminology import conceptmaps, registry, systems
from . import common
from .context import MappingContext

PRIOR_CARE_EXT = "urn:emsinterop:extension:obtained-prior-to-unit-care"

# element id -> (LOINC code, display, unit display, UCUM code, US Core profile)
_QUANTITY_VITALS = {
    "eVitals.10": ("8867-4", "Heart rate", "beats/min", "/min", "us-core-heart-rate"),
    "eVitals.12": ("59408-5", "Oxygen saturation in Arterial blood by Pulse oximetry", "%", "%", "us-core-pulse-oximetry"),
    "eVitals.14": ("9279-1", "Respiratory rate", "breaths/min", "/min", "us-core-respiratory-rate"),
    "eVitals.16": ("19889-5", "Carbon dioxide in Exhaled gas", "mmHg", "mm[Hg]", None),
    "eVitals.18": ("2339-0", "Glucose [Mass/volume] in Blood", "mg/dL", "mg/dL", None),
    "eVitals.24": ("8310-5", "Body temperature", "Cel", "Cel", "us-core-body-temperature"),
    "eVitals.27": ("72514-3", "Pain severity 0-10 verbal numeric rating", "{score}", "{score}", None),
}

_GCS_COMPONENTS = [
    ("eVitals.19", "9267-6", "Glasgow coma score.eye opening"),
    ("eVitals.20", "9270-0", "Glasgow coma score.verbal"),
    ("eVitals.21", "9268-4", "Glasgow coma score.motor"),
]


def _base_observation(
    ctx: MappingContext, group: NemsisGroup, discriminator: str, code: dict
) -> dict:
    obs: dict = {
        "resourceType": "Observation",
        "id": ctx.rid("Observation", "eVitals", group.index, discriminator),
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": systems.OBSERVATION_CATEGORY,
                        "code": "vital-signs",
                        "display": "Vital Signs",
                    }
                ]
            }
        ],
        "code": code,
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
    }
    taken = group.first("eVitals.01")
    if taken is not None and taken.has_value:
        obs["effectiveDateTime"] = taken.value
    # No usable time. Every alternative was checked against the official
    # validator: a value-less `_effectiveDateTime` trips vs-1; omitting
    # effective[x] trips the bp/heartrate profiles' min=1; and a Period trips
    # vs-1 too, because R4's expression `($this as dateTime).toString()
    # .length() >= 8` has no guard for the Period branch it permits.
    #
    # What DOES work is FHIR's variable-precision dateTime: vs-1 asks for >= 8
    # characters, i.e. a DATE is enough. "Measured on 2024-10-07" is true and
    # asserts no time of day the source never recorded — unlike copying the
    # encounter's start timestamp, which would invent precision.
    elif date := common.encounter_date(ctx.encounter_period):
        obs["effectiveDateTime"] = date
    if taken is None or not taken.has_value:
        # Ledger EVERY undated measurement, whether or not we managed to bound
        # it — substituting a period is a real change to what the resource
        # asserts, and a silent substitution is exactly what the
        # never-silently-drop rule exists to prevent.
        nv = taken.nv if taken is not None else None
        bounded = "effectiveDateTime" in obs
        ctx.log(
            "eVitals.01",
            Disposition.SEEDED,
            "no measurement time recorded"
            + (f" (NV {nv})" if nv else "")
            + ("; recorded at the encounter's DATE precision rather than given "
               "a false precise timestamp" if bounded else
               "; effective[x] omitted and the US Core vital-signs claim withheld"),
            "information",
        )
    prior = group.first("eVitals.02")
    if prior is not None and prior.has_value and prior.value == common.YES:
        obs.setdefault("extension", []).append(
            {"url": PRIOR_CARE_EXT, "valueBoolean": True}
        )
    return obs


def _apply_value_quantity(
    obs: dict,
    element: NemsisElement,
    unit: str,
    ucum: str,
    ctx: MappingContext | None = None,
    element_id: str | None = None,
) -> None:
    off_scale = _off_scale_code(element_id or "", element.value)
    if element.has_value and common.is_numeric(element.value):
        obs["valueQuantity"] = common.quantity(element.value, unit, ucum)
    elif element.has_value and off_scale:
        # eVitals.18 'High'/'Low' — XSD-sanctioned: the meter read off its
        # scale. That is a clinical finding, not malformed data, so it is
        # recorded as an interpretation rather than flattened to "error".
        obs["dataAbsentReason"] = common.unusable_value_concept("not-a-number")
        obs["interpretation"] = [
            {"coding": [{"system": common.V3_INTERPRETATION, "code": off_scale,
                         "display": "off scale high" if off_scale == "HX"
                                    else "off scale low"}]}
        ]
        if ctx is not None and element_id:
            ctx.log(element_id, Disposition.SEEDED,
                    f"meter reported {element.value!r} (off-scale); carried as "
                    f"interpretation {off_scale} with no numeric value",
                    "information")
    elif element.has_value:
        # Present but not a number: keep the observation, mark the value
        # unusable. Never abort the PCR over one dirty field.
        obs["dataAbsentReason"] = common.unusable_value_concept("error")
    elif common.is_negative_finding(element):
        obs["interpretation"] = common.negative_interpretation()
    else:
        obs["dataAbsentReason"] = common.absent_reason_concept(element)


#: The ONLY NEMSIS elements whose XSD pattern admits a letter in a numeric
#: slot are eVitals.07 (P/p, palpated) and eVitals.18 (High/Low, off-scale
#: glucose). Verified by sweeping every pattern in the pinned 3.5.0 schemas —
#: this list is complete, not a sample.
_OFF_SCALE = {"HIGH": "HX", "LOW": "LX"}


def _off_scale_code(element_id: str, value: str | None) -> str | None:
    """v3 interpretation code for an off-scale meter reading, else None."""
    if element_id != "eVitals.18":
        return None
    return _OFF_SCALE.get((value or "").strip().upper())


def _is_palpated(value: str | None) -> bool:
    """eVitals.07's XSD-sanctioned non-numeric values: 'P' / 'p' (palpated)."""
    return (value or "").strip().upper() == "P"


def _element_id_of(element, loinc_code: str) -> str:
    return "eVitals.06" if loinc_code == "8480-6" else "eVitals.07"


def _blood_pressure(ctx: MappingContext, group: NemsisGroup) -> dict | None:
    sbp = group.first("eVitals.06")
    dbp = group.first("eVitals.07")
    if sbp is None and dbp is None:
        return None
    palpated = False
    obs = _base_observation(
        ctx, group, "bp", common.loinc("85354-9", "Blood pressure panel with all children optional")
    )
    if common.can_claim_vital_signs(obs):
        common.claim_profiles(obs, "us-core-vital-signs", "us-core-blood-pressure")
    components = []
    for element, code, display in [
        (sbp, "8480-6", "Systolic blood pressure"),
        (dbp, "8462-4", "Diastolic blood pressure"),
    ]:
        # The bp/US Core profiles require BOTH components (value or
        # dataAbsentReason) — an element absent from the source group still
        # yields a component, with the absence explained.
        component: dict = {"code": common.loinc(code, display)}
        if element is not None and element.has_value and common.is_numeric(element.value):
            component["valueQuantity"] = common.quantity(element.value, "mmHg", "mm[Hg]")
        elif element is not None and element.has_value and _is_palpated(element.value):
            # eVitals.07 'P'/'p' is XSD-sanctioned: the BP was obtained by
            # PALPATION, which yields a systolic only. Routine field practice
            # on hypotensive patients — the reading must survive, with the
            # diastolic honestly marked as never measured, not dropped and not
            # crashed on.
            component["dataAbsentReason"] = common.unusable_value_concept("not-performed")
            palpated = True
        elif element is not None and element.has_value:
            component["dataAbsentReason"] = common.unusable_value_concept("error")
            ctx.log(
                _element_id_of(element, code),
                Disposition.INVALID,
                "blood pressure value is neither numeric nor the XSD's palpated "
                "sentinel; carried as dataAbsentReason=error",
                "warning",
            )
        elif element is not None:
            component["dataAbsentReason"] = common.absent_reason_concept(element)
        else:
            component["dataAbsentReason"] = {
                "coding": [{"system": systems.DATA_ABSENT_REASON, "code": "unknown"}]
            }
        components.append(component)
    obs["component"] = components
    method = group.first("eVitals.08")
    if method is not None and method.has_value:
        obs["method"] = conceptmaps.dual_code("eVitals.08", method.value)
    elif palpated:
        # NEMSIS recorded the technique in the value slot rather than
        # eVitals.08; preserve it as the observation's method.
        obs["method"] = {"text": "Palpated"}
    return ctx.add(obs)


def _gcs(ctx: MappingContext, group: NemsisGroup) -> dict | None:
    elements = {eid: group.first(eid) for eid, _, _ in _GCS_COMPONENTS}
    total = group.first("eVitals.23")
    if all(e is None for e in elements.values()) and total is None:
        return None
    obs = _base_observation(ctx, group, "gcs", common.loinc("9269-2", "Glasgow coma score total"))
    components = []
    component_sum = 0
    complete = True
    for eid, code, display in _GCS_COMPONENTS:
        element = elements[eid]
        if element is None:
            complete = False
            continue
        component: dict = {"code": common.loinc(code, display)}
        if element.has_value and common.is_numeric(element.value):
            component["valueQuantity"] = common.quantity(element.value, "{score}", "{score}")
            component_sum += int(float(element.value))
        elif element.has_value:
            component["dataAbsentReason"] = common.unusable_value_concept("error")
            complete = False
        else:
            component["dataAbsentReason"] = common.absent_reason_concept(element)
            complete = False
        components.append(component)
    qualifier = group.first("eVitals.22")  # GCS qualifier (e.g. intubated, sedated)
    if qualifier is not None and qualifier.has_value:
        components.append(
            {
                "code": {
                    "coding": [{"system": systems.NEMSIS, "code": "eVitals.22"}],
                    "text": "Glasgow Coma Score Qualifier",
                },
                "valueCodeableConcept": conceptmaps.dual_code("eVitals.22", qualifier.value),
            }
        )
    if components:
        obs["component"] = components
    if total is not None and total.has_value and common.is_numeric(total.value):
        obs["valueQuantity"] = common.quantity(total.value, "{score}", "{score}")
        if complete and int(float(total.value)) != component_sum:
            ctx.log(
                "eVitals.23",
                Disposition.INVALID,
                f"GCS total {total.value} != component sum {component_sum}",
            )
    elif total is not None and total.has_value:
        obs["dataAbsentReason"] = common.unusable_value_concept("error")
    elif complete and components:
        # typed-helper aggregation: total derivable from complete components
        obs["valueQuantity"] = common.quantity(str(component_sum), "{score}", "{score}")
    elif total is not None:
        obs["dataAbsentReason"] = common.absent_reason_concept(total)
    return ctx.add(obs)


def map_vitals(ctx: MappingContext) -> list[dict]:
    out: list[dict] = []
    for group in ctx.pcr.groups("eVitals", "eVitals.VitalGroup"):
        bp = _blood_pressure(ctx, group)
        if bp is not None:
            out.append(bp)

        for element_id, (code, display, unit, ucum, profile) in _QUANTITY_VITALS.items():
            element = group.first(element_id)
            if element is None:
                continue
            concept = common.loinc(code, display)
            if element_id == "eVitals.12":
                # US Core pulse-ox: primary 59408-5 plus the base SpO2 code.
                concept["coding"].append({"system": systems.LOINC, "code": "2708-6"})
            obs = _base_observation(ctx, group, element_id, concept)
            if profile and common.can_claim_vital_signs(obs):
                common.claim_profiles(obs, "us-core-vital-signs", profile)
            if element_id == "eVitals.27":
                # eVitals.28 Pain Scale Type qualifies the score as its method.
                pain_type = group.first("eVitals.28")
                if pain_type is not None and pain_type.has_value:
                    obs["method"] = conceptmaps.dual_code("eVitals.28", pain_type.value)
            _apply_value_quantity(obs, element, unit, ucum, ctx, element_id)
            out.append(ctx.add(obs))

        gcs = _gcs(ctx, group)
        if gcs is not None:
            out.append(gcs)

        avpu = group.first("eVitals.26")
        if avpu is not None:
            obs = _base_observation(
                ctx,
                group,
                "eVitals.26",
                {
                    "coding": [{"system": systems.NEMSIS, "code": "eVitals.26"}],
                    "text": registry.element_name("eVitals.26")
                    or "Level of Responsiveness (AVPU)",
                },
            )
            if avpu.has_value:
                obs["valueCodeableConcept"] = conceptmaps.dual_code("eVitals.26", avpu.value)
            else:
                obs["dataAbsentReason"] = common.absent_reason_concept(avpu)
            out.append(ctx.add(obs))

        ecg_type = group.first("eVitals.04")
        interpretation_method = group.first("eVitals.05")
        for occurrence, rhythm in enumerate(group.all("eVitals.03")):
            if not (rhythm.has_value or rhythm.nv or rhythm.pn):
                continue
            obs = _base_observation(
                ctx,
                group,
                f"eVitals.03-{occurrence}",
                {
                    "coding": [{"system": systems.NEMSIS, "code": "eVitals.03"}],
                    "text": "Cardiac Rhythm / ECG",
                },
            )
            if rhythm.has_value:
                obs["valueCodeableConcept"] = conceptmaps.dual_code("eVitals.03", rhythm.value)
            else:
                obs["dataAbsentReason"] = common.absent_reason_concept(rhythm)
            if ecg_type is not None and ecg_type.has_value:
                obs["method"] = conceptmaps.dual_code("eVitals.04", ecg_type.value)
            if interpretation_method is not None and interpretation_method.has_value:
                obs.setdefault("component", []).append(
                    {
                        "code": {
                            "coding": [{"system": systems.NEMSIS, "code": "eVitals.05"}],
                            "text": "Method of ECG Interpretation",
                        },
                        "valueCodeableConcept": conceptmaps.dual_code(
                            "eVitals.05", interpretation_method.value
                        ),
                    }
                )
            out.append(ctx.add(obs))

        # Stroke scale (eVitals.29 score + .30 type) and reperfusion checklist
        # (eVitals.31): coded scores within the vitals set; NV -> dataAbsentReason.
        stroke = group.first("eVitals.29")
        if stroke is not None and (stroke.has_value or stroke.nv or stroke.pn):
            obs = _base_observation(
                ctx,
                group,
                "eVitals.29",
                {
                    "coding": [{"system": systems.NEMSIS, "code": "eVitals.29"}],
                    "text": registry.element_name("eVitals.29") or "Stroke Scale Score",
                },
            )
            if stroke.has_value:
                obs["valueCodeableConcept"] = conceptmaps.dual_code("eVitals.29", stroke.value)
            else:
                obs["dataAbsentReason"] = common.absent_reason_concept(stroke)
            stroke_type = group.first("eVitals.30")
            if stroke_type is not None and stroke_type.has_value:
                obs["method"] = conceptmaps.dual_code("eVitals.30", stroke_type.value)
            out.append(ctx.add(obs))

        reperfusion = group.first("eVitals.31")
        if reperfusion is not None and (reperfusion.has_value or reperfusion.nv or reperfusion.pn):
            obs = _base_observation(
                ctx,
                group,
                "eVitals.31",
                {
                    "coding": [{"system": systems.NEMSIS, "code": "eVitals.31"}],
                    "text": registry.element_name("eVitals.31") or "Reperfusion Checklist",
                },
            )
            if reperfusion.has_value:
                obs["valueCodeableConcept"] = conceptmaps.dual_code(
                    "eVitals.31", reperfusion.value
                )
            else:
                obs["dataAbsentReason"] = common.absent_reason_concept(reperfusion)
            out.append(ctx.add(obs))
    return out
