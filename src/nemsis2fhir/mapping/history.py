"""eHistory -> AllergyIntolerance / Condition / MedicationStatement / Observation.

The flagship PN case lives here: 8801013 No Known Drug Allergy -> a negated
AllergyIntolerance (SNOMED 409137002 dual-coded with the NEMSIS PN) — never a
skipped element. eHistory.17 substance-use observations are DS4P-tagged at
creation (the mapper tags; fhirEngine enforces).
"""

from __future__ import annotations

from ..issues import Disposition
from ..model import NemsisElement
from ..terminology import nv_pn, registry, systems
from . import common
from .context import MappingContext

SNOMED_NKDA = "409137002"  # No known drug allergy (situation)
SNOMED_NO_CURRENT_PROBLEMS = "160245001"  # No current problems or disability


def _allergy(
    ctx: MappingContext,
    element: NemsisElement,
    discriminator: str,
    category: str,
    code_system: str,
) -> dict | None:
    allergy: dict = {
        "resourceType": "AllergyIntolerance",
        "id": ctx.rid("AllergyIntolerance", discriminator),
        "clinicalStatus": {
            "coding": [{"system": systems.ALLERGY_CLINICAL, "code": "active"}]
        },
        "verificationStatus": {
            "coding": [{"system": systems.ALLERGY_VERIFICATION, "code": "confirmed"}]
        },
        "category": [category],
        "patient": ctx.patient_ref(),
    }
    if element.has_value:
        allergy["code"] = {"coding": [{"system": code_system, "code": element.value}]}
    elif element.pn == nv_pn.PN_NO_KNOWN_DRUG_ALLERGY:
        allergy["code"] = {
            "coding": [
                {
                    "system": systems.SNOMED,
                    "code": SNOMED_NKDA,
                    "display": "No known drug allergy",
                },
                nv_pn.pn_coding(element.pn),
            ],
            "text": "No Known Drug Allergy",
        }
    elif element.pn == nv_pn.PN_NONE_REPORTED:
        allergy["code"] = nv_pn.pn_concept(element.pn)
    elif element.nv:
        ctx.log(
            element.element_id,
            Disposition.MAPPED,
            f"NV {element.nv} — no AllergyIntolerance emitted; "
            "escalates to Allergies section emptyReason",
            "information",
        )
        return None
    else:
        return None
    common.claim_profiles(allergy, "us-core-allergyintolerance")
    return ctx.add(allergy)


def map_history(ctx: MappingContext) -> list[dict]:
    out: list[dict] = []
    pcr = ctx.pcr

    for index, barrier in enumerate(pcr.all("eHistory.01")):
        if not barrier.has_value:
            continue  # NV filler consumed by the read
        obs = common.course_observation(ctx, barrier, f"eHistory.01-{index}")
        if obs is not None:
            obs["category"] = [
                {
                    "coding": [
                        {"system": systems.OBSERVATION_CATEGORY, "code": "social-history"}
                    ]
                }
            ]
            out.append(obs)

    for index, med_allergy in enumerate(pcr.all("eHistory.06")):
        allergy = _allergy(
            ctx, med_allergy, f"medication-{index}", "medication", systems.RXNORM
        )
        if allergy is not None:
            out.append(allergy)
    for index, env_allergy in enumerate(pcr.all("eHistory.07")):
        allergy = _allergy(
            ctx, env_allergy, f"environment-{index}", "environment", systems.SNOMED
        )
        if allergy is not None:
            out.append(allergy)

    for index, pmh in enumerate(pcr.all("eHistory.08")):
        condition: dict | None = None
        if pmh.has_value:
            # eHistory.08 is ICD-10-CM in 3.5.0 (XSD pattern-verified).
            condition = {
                "code": {"coding": [{"system": systems.ICD10CM, "code": pmh.value}]}
            }
        elif pmh.pn == nv_pn.PN_NONE_REPORTED:
            condition = {
                "code": {
                    "coding": [
                        {
                            "system": systems.SNOMED,
                            "code": SNOMED_NO_CURRENT_PROBLEMS,
                            "display": "No current problems or disability",
                        },
                        nv_pn.pn_coding(pmh.pn),
                    ],
                    "text": "No past medical history reported",
                }
            }
        if condition is None:
            continue
        common.claim_profiles(condition, "us-core-condition-problems-health-concerns")
        condition.update(
            {
                "resourceType": "Condition",
                "id": ctx.rid("Condition", f"pmh-{index}"),
                "clinicalStatus": {
                    "coding": [{"system": systems.CONDITION_CLINICAL, "code": "active"}]
                },
                "category": [
                    {
                        "coding": [
                            {
                                "system": systems.CONDITION_CATEGORY,
                                "code": "problem-list-item",
                            }
                        ]
                    }
                ],
                "subject": ctx.patient_ref(),
            }
        )
        out.append(ctx.add(condition))

    for index, med in enumerate(pcr.all("eHistory.12")):
        statement: dict = {
            "resourceType": "MedicationStatement",
            "id": ctx.rid("MedicationStatement", index),
            "subject": ctx.patient_ref(),
        }
        if med.has_value:
            statement["status"] = "active"
            statement["medicationCodeableConcept"] = {
                "coding": [{"system": systems.RXNORM, "code": med.value}]
            }
        elif med.pn == nv_pn.PN_NONE_REPORTED:
            statement["status"] = "unknown"
            statement["medicationCodeableConcept"] = nv_pn.pn_concept(med.pn)
        elif med.nv:
            statement["status"] = "unknown"
            statement["medicationCodeableConcept"] = common.absent_reason_concept(med)
        else:
            continue
        out.append(ctx.add(statement))

    for index, indicator in enumerate(pcr.all("eHistory.17")):
        if not (indicator.has_value or indicator.nv or indicator.pn):
            continue
        obs: dict = {
            "resourceType": "Observation",
            "id": ctx.rid("Observation", f"eHistory.17-{index}"),
            "status": "final",
            "category": [
                {
                    "coding": [
                        {"system": systems.OBSERVATION_CATEGORY, "code": "social-history"}
                    ]
                }
            ],
            "code": {
                "coding": [{"system": systems.NEMSIS, "code": "eHistory.17"}],
                "text": registry.element_name("eHistory.17")
                or "Alcohol/Drug Use Indicators",
            },
            "subject": ctx.patient_ref(),
            "encounter": ctx.encounter_ref(),
        }
        if indicator.has_value:
            obs["valueCodeableConcept"] = {
                "coding": [registry.nemsis_coding("eHistory.17", indicator.value)],
                "text": registry.display("eHistory.17", indicator.value),
            }
            # DS4P: substance-use content is 42 CFR Part 2-sensitive.
            # The mapper tags; fhirEngine enforces (hard rule).
            obs["meta"] = {
                "security": [
                    {"system": systems.V3_CONFIDENTIALITY, "code": "R", "display": "restricted"},
                    {"system": systems.V3_ACT_CODE, "code": "ETH", "display": "substance abuse information sensitivity"},
                ]
            }
        else:
            obs["dataAbsentReason"] = common.absent_reason_concept(indicator)
        out.append(ctx.add(obs))

    pregnancy = pcr.first("eHistory.18")
    if pregnancy is not None and (pregnancy.has_value or pregnancy.nv):
        obs = {
            "resourceType": "Observation",
            "id": ctx.rid("Observation", "eHistory.18"),
            "status": "final",
            "code": common.loinc("82810-3", "Pregnancy status"),
            "subject": ctx.patient_ref(),
            "encounter": ctx.encounter_ref(),
        }
        if pregnancy.has_value:
            obs["valueCodeableConcept"] = {
                "coding": [registry.nemsis_coding("eHistory.18", pregnancy.value)],
                "text": registry.display("eHistory.18", pregnancy.value),
            }
        else:
            obs["dataAbsentReason"] = common.absent_reason_concept(pregnancy)
        out.append(ctx.add(obs))

    return out
