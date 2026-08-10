"""eSituation -> Condition / Observation.

eSituation.11 Provider's Primary Impression is the principal
encounter-diagnosis Condition; .12 secondaries are additional Conditions; the
chief complaint (.04, free text) is its own Condition carrying symptom onset
(.01). Acuity and symptoms become Observations; PN SymptomNotPresent ->
negative interpretation (pertinent negative preserved).

Terminology note (verified against the pinned 3.5.0 XSD, which pattern-checks
these fields): impressions (.11/.12) and symptoms (.09/.10) are ICD-10-CM in
NEMSIS 3.5.0 — NOT SNOMED as the architecture doc §3 states. Pass-through with
the ICD-10-CM system URI.
"""

from __future__ import annotations

from ..issues import Disposition
from ..model import NemsisElement
from ..terminology import conceptmaps, registry, systems
from . import common
from .context import MappingContext


def _condition(ctx: MappingContext, discriminator: str, code: dict, category: str) -> dict:
    return {
        "resourceType": "Condition",
        "id": ctx.rid("Condition", discriminator),
        "clinicalStatus": {
            "coding": [{"system": systems.CONDITION_CLINICAL, "code": "active"}]
        },
        "category": [
            {
                "coding": [
                    {
                        "system": systems.CONDITION_CATEGORY,
                        "code": category,
                    }
                ]
            }
        ],
        "code": code,
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
    }


def _symptom_observation(ctx: MappingContext, element: NemsisElement, discriminator: str) -> dict:
    obs: dict = {
        "resourceType": "Observation",
        "id": ctx.rid("Observation", "eSituation", discriminator),
        "status": "final",
        "code": {
            "coding": [{"system": systems.NEMSIS, "code": element.element_id}],
            "text": registry.element_name(element.element_id) or element.element_id,
        },
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
    }
    if element.has_value:
        # Symptoms are ICD-10-CM-coded in the 3.5.0 source (XSD-verified).
        obs["valueCodeableConcept"] = {
            "coding": [{"system": systems.ICD10CM, "code": element.value}]
        }
    elif common.is_negative_finding(element):
        obs["valueCodeableConcept"] = {
            "coding": [
                {"system": systems.NEMSIS, "code": element.pn},
            ],
            "text": "Symptom not present (pertinent negative)",
        }
        obs["interpretation"] = common.negative_interpretation()
    else:
        obs["dataAbsentReason"] = common.absent_reason_concept(element)
    return ctx.add(obs)


def map_situation(ctx: MappingContext) -> list[dict]:
    out: list[dict] = []
    pcr = ctx.pcr

    primary = pcr.first("eSituation.11")
    if primary is not None and primary.has_value:
        condition = _condition(
            ctx,
            "primary-impression",
            {"coding": [{"system": systems.ICD10CM, "code": primary.value}]},
            "encounter-diagnosis",
        )
        onset = pcr.first("eSituation.01")
        if onset is not None and onset.has_value:
            condition["onsetDateTime"] = common.fhir_datetime(onset.value)
        common.claim_profiles(condition, "us-core-condition-encounter-diagnosis")
        out.append(ctx.add(condition))
    elif primary is not None and (primary.nv or primary.pn):
        ctx.log(
            "eSituation.11",
            Disposition.MAPPED,
            f"primary impression carries {'NV ' + primary.nv if primary.nv else 'PN ' + (primary.pn or '')};"
            " no Condition emitted — escalates to section emptyReason",
            "information",
        )

    for index, secondary in enumerate(pcr.all("eSituation.12")):
        if secondary.has_value:
            condition = _condition(
                ctx,
                f"secondary-impression-{index}",
                {"coding": [{"system": systems.ICD10CM, "code": secondary.value}]},
                "encounter-diagnosis",
            )
            common.claim_profiles(condition, "us-core-condition-encounter-diagnosis")
            out.append(ctx.add(condition))

    complaint = pcr.first("eSituation.04")
    if complaint is not None and complaint.has_value:
        condition = _condition(
            ctx, "chief-complaint", {"text": complaint.value}, "problem-list-item"
        )
        complaint_type = pcr.first("eSituation.03")
        if complaint_type is not None and complaint_type.has_value:
            condition["category"].append(
                conceptmaps.dual_code("eSituation.03", complaint_type.value)
            )
        body_sites = []
        site = pcr.first("eSituation.07")
        if site is not None and site.has_value:
            body_sites.append(conceptmaps.dual_code("eSituation.07", site.value))
        organ_system = pcr.first("eSituation.08")
        if organ_system is not None and organ_system.has_value:
            body_sites.append(conceptmaps.dual_code("eSituation.08", organ_system.value))
        if body_sites:
            condition["bodySite"] = body_sites
        common.claim_profiles(condition, "us-core-condition-problems-health-concerns")
        out.append(ctx.add(condition))

    injury_possible = pcr.first("eSituation.02")
    if injury_possible is not None and injury_possible.has_value:
        obs = common.course_observation(ctx, injury_possible, "eSituation.02", category="exam")
        if obs is not None:
            out.append(obs)

    acuity = pcr.first("eSituation.13")
    if acuity is not None and (acuity.has_value or acuity.nv):
        obs: dict = {
            "resourceType": "Observation",
            "id": ctx.rid("Observation", "eSituation.13"),
            "status": "final",
            "code": {
                "coding": [{"system": systems.NEMSIS, "code": "eSituation.13"}],
                "text": "Initial Patient Acuity",
            },
            "subject": ctx.patient_ref(),
            "encounter": ctx.encounter_ref(),
        }
        if acuity.has_value:
            obs["valueCodeableConcept"] = conceptmaps.dual_code("eSituation.13", acuity.value)
        else:
            obs["dataAbsentReason"] = common.absent_reason_concept(acuity)
        out.append(ctx.add(obs))

    symptom = pcr.first("eSituation.09")
    if symptom is not None and (symptom.has_value or symptom.pn or symptom.nv):
        out.append(_symptom_observation(ctx, symptom, "primary-symptom"))
    for index, other in enumerate(pcr.all("eSituation.10")):
        if other.has_value or other.pn:
            out.append(_symptom_observation(ctx, other, f"other-symptom-{index}"))

    lkw = pcr.first("eSituation.18")
    if lkw is not None and lkw.has_value:
        out.append(
            ctx.add(
                {
                    "resourceType": "Observation",
                    "id": ctx.rid("Observation", "eSituation.18"),
                    "status": "final",
                    "code": {
                        "coding": [{"system": systems.NEMSIS, "code": "eSituation.18"}],
                        "text": "Date/Time Last Known Well",
                    },
                    "subject": ctx.patient_ref(),
                    "encounter": ctx.encounter_ref(),
                    "valueDateTime": common.fhir_datetime(lkw.value),
                }
            )
        )
    return out
