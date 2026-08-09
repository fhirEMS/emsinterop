"""eExam -> Observations: weight, length-based tape, and regional assessments.

eExam.01 Weight (kg) and eExam.02 Length Based Tape Measure (Broselow color)
are the pediatric length-based dosing anchors. Regional assessment findings
(.04-.25, value-coded — NEMSIS represents "not done"/"normal" as codes, not
nil-PN) become exam-category Observations sharing the AssessmentGroup's .03
timestamp.
"""

from __future__ import annotations

from ..model import NemsisGroup
from ..terminology import conceptmaps, registry, systems
from . import common
from .context import MappingContext

# Regional assessment finding elements inside an AssessmentGroup (any nesting).
_ASSESSMENT_FINDINGS = [
    "eExam.04",  # skin
    "eExam.05",  # head
    "eExam.06",  # face
    "eExam.07",  # neck
    "eExam.09",  # heart
    "eExam.10", "eExam.11",  # abdomen side/finding
    "eExam.12",  # pelvis/GU
    "eExam.13", "eExam.14",  # spine side/finding
    "eExam.15", "eExam.16",  # extremity side/finding
    "eExam.17", "eExam.18",  # eye side/finding
    "eExam.19",  # mental status
    "eExam.20",  # neurological
    "eExam.22", "eExam.23",  # lung side/finding
    "eExam.24", "eExam.25",  # chest side/finding
]


def _weight_observation(ctx: MappingContext) -> dict | None:
    weight = ctx.pcr.first("eExam.01")
    if weight is None or not (weight.has_value or weight.nv or weight.pn):
        return None
    obs: dict = {
        "resourceType": "Observation",
        "id": ctx.rid("Observation", "eExam.01"),
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
        "code": common.loinc("29463-7", "Body weight"),
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
    }
    # Vital-signs profiles require effective[x]; eExam.01 has no timestamp of
    # its own, so use the first assessment time, else arrival at patient/scene.
    effective = None
    for candidate in ("eExam.03", "eTimes.07", "eTimes.06"):
        element = ctx.pcr.first(candidate)
        if element is not None and element.has_value:
            effective = element.value
            break
    if effective:
        obs["effectiveDateTime"] = effective
    elif date := common.encounter_date(ctx.encounter_period):
        # Reduced precision, not absence — see mapping/vitals.py.
        obs["effectiveDateTime"] = date
    else:
        obs["_effectiveDateTime"] = {
            "extension": [
                {"url": systems.DATA_ABSENT_REASON_EXT, "valueCode": "unknown"}
            ]
        }
    if weight.has_value and common.is_numeric(weight.value):
        obs["valueQuantity"] = common.quantity(weight.value, "kg", "kg")
        if common.can_claim_vital_signs(obs):
            common.claim_profiles(obs, "us-core-vital-signs", "us-core-body-weight")
        else:
            ctx.log("eExam.01", Disposition.SEEDED,
                    "no usable measurement time for body weight; effective[x] "
                    "omitted and the US Core claim withheld (invariant vs-1)",
                    "information")
    elif weight.has_value:
        obs["dataAbsentReason"] = common.unusable_value_concept("error")
    else:
        obs["dataAbsentReason"] = common.absent_reason_concept(weight)
    return ctx.add(obs)


def _tape_observation(ctx: MappingContext) -> dict | None:
    tape = ctx.pcr.first("eExam.02")
    if tape is None or not (tape.has_value or tape.nv or tape.pn):
        return None
    obs: dict = {
        "resourceType": "Observation",
        "id": ctx.rid("Observation", "eExam.02"),
        "status": "final",
        "category": [
            {"coding": [{"system": systems.OBSERVATION_CATEGORY, "code": "exam"}]}
        ],
        "code": {
            "coding": [{"system": systems.NEMSIS, "code": "eExam.02"}],
            "text": registry.element_name("eExam.02") or "Length Based Tape Measure",
        },
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
    }
    if tape.has_value:
        obs["valueCodeableConcept"] = conceptmaps.dual_code("eExam.02", tape.value)
    else:
        obs["dataAbsentReason"] = common.absent_reason_concept(tape)
    return ctx.add(obs)


def _assessment_observations(ctx: MappingContext, group: NemsisGroup) -> list[dict]:
    out: list[dict] = []
    taken = group.first("eExam.03")
    for element_id in _ASSESSMENT_FINDINGS:
        for occurrence, element in enumerate(group.all(element_id)):
            if not element.has_value:
                continue
            obs: dict = {
                "resourceType": "Observation",
                "id": ctx.rid("Observation", "eExam", group.index, element_id, occurrence),
                "status": "final",
                "category": [
                    {"coding": [{"system": systems.OBSERVATION_CATEGORY, "code": "exam"}]}
                ],
                "code": {
                    "coding": [{"system": systems.NEMSIS, "code": element_id}],
                    "text": registry.element_name(element_id) or element_id,
                },
                "subject": ctx.patient_ref(),
                "encounter": ctx.encounter_ref(),
            }
            if taken is not None and taken.has_value:
                obs["effectiveDateTime"] = taken.value
            common.apply_smart_value(obs, element)
            out.append(ctx.add(obs))
    return out


def map_exam(ctx: MappingContext) -> list[dict]:
    out: list[dict] = []
    section = ctx.pcr.section("eExam")
    if section is None:
        return out
    weight = _weight_observation(ctx)
    if weight is not None:
        out.append(weight)
    tape = _tape_observation(ctx)
    if tape is not None:
        out.append(tape)
    for group in ctx.pcr.groups("eExam", "eExam.AssessmentGroup"):
        out.extend(_assessment_observations(ctx, group))
    # eExam.21 (stroke scale result, legacy slot in some builds): read/consume.
    ctx.pcr.first("eExam.21")
    return out
