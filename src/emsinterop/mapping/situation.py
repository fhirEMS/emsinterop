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

    # Symptom onset (.01) is resolved ONCE, up front, and carried by whichever
    # Condition this document turns out to have. It used to be read inside the
    # primary-impression branch, so an NV/PN impression — routine in real
    # exports — meant a national Required element was never even looked at, and
    # the time the patient's symptoms began was dropped without a ledger entry.
    onset = pcr.first("eSituation.01")
    onset_dt = (
        common.fhir_datetime(onset.value)
        if onset is not None and onset.has_value
        else None
    )
    onset_carried = False

    # Body site (.07) and organ system (.08) had the same defect as onset: read
    # only inside the chief-complaint branch, so a document with no complaint
    # never touched them. Resolve them up front for the same reason.
    site = pcr.first("eSituation.07")
    organ_system = pcr.first("eSituation.08")
    body_sites = [
        conceptmaps.dual_code(element.element_id, element.value)
        for element in (site, organ_system)
        if element is not None and element.has_value
    ]
    body_sites_carried = False

    primary = pcr.first("eSituation.11")
    if primary is not None and primary.has_value:
        condition = _condition(
            ctx,
            "primary-impression",
            {"coding": [{"system": systems.ICD10CM, "code": primary.value}]},
            "encounter-diagnosis",
        )
        if onset_dt is not None:
            condition["onsetDateTime"] = onset_dt
            onset_carried = True
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
        if body_sites:
            condition["bodySite"] = body_sites
            body_sites_carried = True
        if onset_dt is not None:
            condition["onsetDateTime"] = onset_dt
            onset_carried = True
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

    # No Condition existed to carry onset — an impression that is NV/PN with no
    # chief complaint, which is a shape real exports take. Rather than drop the
    # time the symptoms began, emit it the same way Last Known Well above is
    # emitted: a standalone dated Observation. Same kind of fact, proven shape.
    # Anatomic location belongs to a Condition; with none emitted there is no
    # valid FHIR home for it. Ledger it as a deferral naming the reason rather
    # than letting it fall through to an "unmapped" warning.
    if body_sites and not body_sites_carried:
        for element in (site, organ_system):
            if element is not None and element.has_value:
                ctx.log(
                    element.element_id,
                    Disposition.DEFERRED,
                    "anatomic location has no Condition to attach to (no"
                    " impression and no chief complaint in this record)",
                    "information",
                )

    if onset is not None and not onset_carried:
        if onset_dt is not None:
            out.append(
                ctx.add(
                    {
                        "resourceType": "Observation",
                        "id": ctx.rid("Observation", "eSituation.01"),
                        "status": "final",
                        "code": {
                            "coding": [
                                {"system": systems.NEMSIS, "code": "eSituation.01"}
                            ],
                            "text": "Date/Time of Symptom Onset",
                        },
                        "subject": ctx.patient_ref(),
                        "encounter": ctx.encounter_ref(),
                        "valueDateTime": onset_dt,
                    }
                )
            )
            ctx.log(
                "eSituation.01",
                Disposition.MAPPED,
                "no Condition available to carry onset; emitted as a standalone"
                " Observation so the onset time is not lost",
                "information",
            )
        else:
            ctx.log(
                "eSituation.01",
                Disposition.SEEDED,
                "symptom onset carries "
                f"{'NV ' + onset.nv if onset.nv else 'PN ' + (onset.pn or 'no value')}"
                "; nothing to date",
                "information",
            )
    return out
