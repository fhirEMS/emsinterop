"""eMedications -> MedicationAdministration (RxNorm pass-through).

One MedicationAdministration per MedicationGroup, effective = eMedications.01.
PN on eMedications.03 (contraindicated / refused / denied by order / already
taken...) -> status=not-done + statusReason — the negative IS the clinical
content. Response/complication become Observations partOf the administration.
"""

from __future__ import annotations

from ..issues import Disposition
from ..model import NemsisGroup
from ..terminology import conceptmaps, nv_pn, registry, systems
from . import common
from .context import MappingContext
from .crew import ensure_practitioner
from .vitals import PRIOR_CARE_EXT


def _response_observation(
    ctx: MappingContext, group: NemsisGroup, element_id: str, label: str, med_admin: dict
) -> dict | None:
    element = group.first(element_id)
    if element is None or not (element.has_value or element.pn):
        return None
    obs: dict = {
        "resourceType": "Observation",
        "id": ctx.rid("Observation", "eMedications", group.index, element_id),
        "status": "final",
        "code": {
            "coding": [{"system": systems.NEMSIS, "code": element_id}],
            "text": registry.element_name(element_id) or label,
        },
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
        "partOf": [{"reference": f"MedicationAdministration/{med_admin['id']}"}],
    }
    if element.has_value:
        obs["valueCodeableConcept"] = conceptmaps.dual_code(element_id, element.value)
    else:
        # The 3.5.0 XSD permits only NV here (no PN on .07/.08).
        obs["dataAbsentReason"] = common.absent_reason_concept(element)
    return ctx.add(obs)


def map_medications(ctx: MappingContext) -> list[dict]:
    out: list[dict] = []
    for group in ctx.pcr.groups("eMedications", "eMedications.MedicationGroup"):
        medication = group.first("eMedications.03")
        if medication is None:
            continue

        admin: dict = {
            "resourceType": "MedicationAdministration",
            "id": ctx.rid("MedicationAdministration", group.index),
            "subject": ctx.patient_ref(),
            "context": ctx.encounter_ref(),
        }

        taken = group.first("eMedications.01")
        if taken is not None and taken.has_value:
            admin["effectiveDateTime"] = common.fhir_datetime(taken.value)
        elif taken is not None and taken.nv:
            admin["_effectiveDateTime"] = common.primitive_absent_extension(taken)

        if medication.has_value:
            # RxNorm-coded in source: pass through with correct system, dual-coded.
            admin["status"] = "completed"
            admin["medicationCodeableConcept"] = {
                "coding": [{"system": systems.RXNORM, "code": medication.value}]
            }
        elif medication.pn:
            # Pertinent negative: medication NOT given, and why.
            admin["status"] = "not-done"
            admin["statusReason"] = [nv_pn.pn_concept(medication.pn)]
            admin["medicationCodeableConcept"] = {
                "coding": [nv_pn.pn_coding(medication.pn)],
                "text": nv_pn.PN_DISPLAY.get(medication.pn),
            }
        else:
            admin["status"] = "unknown"
            admin["medicationCodeableConcept"] = common.absent_reason_concept(medication)

        prior = group.first("eMedications.02")
        if prior is not None and prior.has_value and prior.value == common.YES:
            admin.setdefault("extension", []).append(
                {"url": PRIOR_CARE_EXT, "valueBoolean": True}
            )

        dosage: dict = {}
        route = group.first("eMedications.04")
        if route is not None and route.has_value:
            dosage["route"] = conceptmaps.dual_code(
                "eMedications.04", route.value, "cm-nemsis-medroute"
            )
        dose = group.first("eMedications.05")
        unit = group.first("eMedications.06")
        if dose is not None and dose.has_value:
            unit_display = (
                registry.display("eMedications.06", unit.value)
                if unit is not None and unit.has_value
                else None
            )
            if common.is_numeric(dose.value):
                dosage["dose"] = common.quantity(dose.value, unit_display)
            else:
                ctx.log("eMedications.05", Disposition.INVALID,
                        "non-numeric medication dose; dose omitted from dosage",
                        "warning")
        if dosage and admin["status"] != "not-done":
            admin["dosage"] = dosage

        performers = []
        crew = group.first("eMedications.09")
        role = group.first("eMedications.10")  # read unconditionally: role can
        # be recorded (or NV) even when no crew id is documented
        if crew is not None and crew.has_value:
            practitioner_id = ensure_practitioner(ctx, crew.value)
            performer: dict = {
                "actor": {"reference": f"Practitioner/{practitioner_id}"}
            }
            if role is not None and role.has_value:
                performer["function"] = conceptmaps.dual_code("eMedications.10", role.value)
            performers.append(performer)
        if performers:
            admin["performer"] = performers

        ctx.add(admin)
        out.append(admin)
        _response_observation(ctx, group, "eMedications.07", "Response to Medication", admin)
        _response_observation(ctx, group, "eMedications.08", "Medication Complication", admin)
    return out
