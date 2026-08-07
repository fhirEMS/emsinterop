"""eInjury -> Condition (cause of injury) + Observation cluster.

eInjury.01 Cause of Injury is ICD-10-CM external-cause coded -> Condition.
Mechanism/trauma-criteria/detail elements (.02-.10) become Observations when
valued. ACN telematics (.11-.29) stay deferred (coverage sweep ledgers them).
NV Not-Applicable filler (no injury per eSituation.02) is read and consumed.
"""

from __future__ import annotations

from ..terminology import systems
from . import common
from .context import MappingContext

_INJURY_OBSERVATION_ELEMENTS = [
    "eInjury.02",  # mechanism of injury
    "eInjury.03",  # trauma triage criteria (high risk)
    "eInjury.04",  # trauma triage criteria (moderate risk)
    "eInjury.05",  # area of vehicle impact
    "eInjury.06",  # seat row location
    "eInjury.07",  # use of occupant safety equipment
    "eInjury.08",  # airbag deployment
    "eInjury.09",  # height of fall
    "eInjury.10",  # PPE use
]


def map_injury(ctx: MappingContext) -> list[dict]:
    out: list[dict] = []
    section = ctx.pcr.section("eInjury")
    if section is None:
        return out

    for index, cause in enumerate(ctx.pcr.all("eInjury.01")):
        if not cause.has_value:
            continue  # NV filler: consumed by the read; no injury to describe
        condition: dict = {
            "resourceType": "Condition",
            "id": ctx.rid("Condition", f"injury-cause-{index}"),
            "clinicalStatus": {
                "coding": [{"system": systems.CONDITION_CLINICAL, "code": "active"}]
            },
            "category": [
                {
                    "coding": [
                        {
                            "system": systems.CONDITION_CATEGORY,
                            "code": "encounter-diagnosis",
                        }
                    ]
                }
            ],
            "code": {"coding": [{"system": systems.ICD10CM, "code": cause.value}]},
            "subject": ctx.patient_ref(),
            "encounter": ctx.encounter_ref(),
        }
        common.claim_profiles(condition, "us-core-condition-encounter-diagnosis")
        out.append(ctx.add(condition))

    for element_id in _INJURY_OBSERVATION_ELEMENTS:
        for occurrence, element in enumerate(ctx.pcr.all(element_id)):
            created = common.course_observation(
                ctx, element, f"{element_id}-{occurrence}", category="exam"
            )
            if created is not None:
                out.append(created)
    return out
