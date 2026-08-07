"""eArrest -> Observation cluster (cardiac arrest gate + arrest course).

eArrest.01 gates the panel: when "No" (3001001), the remaining required-
nillable elements arrive as NV Not-Applicable structural filler — they are
read (consumed/accounted) but produce no resources. When an arrest occurred,
every valued element becomes an Observation; the arrest timeline datetimes
(.14 ROSC / .18 arrest onset) carry valueDateTime.
"""

from __future__ import annotations

from ..terminology import conceptmaps, systems
from . import common
from .context import MappingContext

ARREST_NO = "3001001"

# Every eArrest element in the 3.5.0 XSD, read unconditionally so the
# coverage sweep sees the whole panel as consumed.
_ARREST_ELEMENTS = [
    "eArrest.01", "eArrest.02", "eArrest.03", "eArrest.04", "eArrest.07",
    "eArrest.09", "eArrest.10", "eArrest.11", "eArrest.12", "eArrest.13",
    "eArrest.14", "eArrest.15", "eArrest.16", "eArrest.17", "eArrest.18",
    "eArrest.19", "eArrest.20", "eArrest.21", "eArrest.22",
]


def map_arrest(ctx: MappingContext) -> list[dict]:
    out: list[dict] = []
    section = ctx.pcr.section("eArrest")
    if section is None:
        return out

    elements = {eid: ctx.pcr.all(eid) for eid in _ARREST_ELEMENTS}

    gate = elements["eArrest.01"][0] if elements["eArrest.01"] else None
    if gate is None:
        return out

    # The gate itself is always represented — "no cardiac arrest" is clinical
    # content (a pertinent negative at panel scale), not filler.
    obs: dict = {
        "resourceType": "Observation",
        "id": ctx.rid("Observation", "eArrest.01"),
        "status": "final",
        "category": [
            {"coding": [{"system": systems.OBSERVATION_CATEGORY, "code": "exam"}]}
        ],
        "code": {
            "coding": [{"system": systems.NEMSIS, "code": "eArrest.01"}],
            "text": "Cardiac Arrest",
        },
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
    }
    if gate.has_value:
        obs["valueCodeableConcept"] = conceptmaps.dual_code("eArrest.01", gate.value)
        if gate.value == ARREST_NO:
            obs["interpretation"] = common.negative_interpretation()
    else:
        obs["dataAbsentReason"] = common.absent_reason_concept(gate)
    out.append(ctx.add(obs))

    # Sub-elements: valued -> Observation; NV filler consumed by the read above.
    for element_id, occurrences in elements.items():
        if element_id == "eArrest.01":
            continue
        for occurrence, element in enumerate(occurrences):
            created = common.course_observation(
                ctx, element, f"{element_id}-{occurrence}", category="exam"
            )
            if created is not None:
                out.append(created)
    return out
