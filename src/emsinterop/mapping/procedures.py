"""eProcedures -> Procedure (SNOMED pass-through).

One Procedure per ProcedureGroup, performed = eProcedures.01. PN on
eProcedures.03 -> status=not-done + statusReason (never dropped). Attempts and
response become Observations partOf the Procedure.
"""

from __future__ import annotations

from ..model import NemsisGroup
from ..terminology import conceptmaps, nv_pn, registry, systems
from . import common
from .context import MappingContext
from .crew import ensure_practitioner
from .vitals import PRIOR_CARE_EXT


def _part_of_observation(
    ctx: MappingContext,
    group: NemsisGroup,
    element_id: str,
    label: str,
    procedure: dict,
    value_kind: str,
) -> dict | None:
    element = group.first(element_id)
    if element is None or not (element.has_value or element.pn):
        return None
    obs: dict = {
        "resourceType": "Observation",
        "id": ctx.rid("Observation", "eProcedures", group.index, element_id),
        "status": "final",
        "code": {
            "coding": [{"system": systems.NEMSIS, "code": element_id}],
            "text": registry.element_name(element_id) or label,
        },
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
        "partOf": [{"reference": f"Procedure/{procedure['id']}"}],
    }
    if element.has_value:
        if value_kind == "integer" and common.is_numeric(element.value):
            obs["valueInteger"] = int(float(element.value))
        elif value_kind == "integer":
            obs["dataAbsentReason"] = common.unusable_value_concept("error")
        else:
            obs["valueCodeableConcept"] = conceptmaps.dual_code(element_id, element.value)
    else:
        obs["dataAbsentReason"] = common.absent_reason_concept(element)
    return ctx.add(obs)


def map_procedures(ctx: MappingContext) -> list[dict]:
    out: list[dict] = []
    for group in ctx.pcr.groups("eProcedures", "eProcedures.ProcedureGroup"):
        code_element = group.first("eProcedures.03")
        if code_element is None:
            continue

        procedure: dict = {
            "resourceType": "Procedure",
            "id": ctx.rid("Procedure", group.index),
            "subject": ctx.patient_ref(),
            "encounter": ctx.encounter_ref(),
        }

        performed = group.first("eProcedures.01")
        if performed is not None and performed.has_value:
            procedure["performedDateTime"] = common.fhir_datetime(performed.value)
        elif performed is not None and performed.nv:
            procedure["_performedDateTime"] = common.primitive_absent_extension(performed)

        if code_element.has_value:
            procedure["status"] = "completed"
            procedure["code"] = {
                "coding": [{"system": systems.SNOMED, "code": code_element.value}]
            }
        elif code_element.pn:
            procedure["status"] = "not-done"
            procedure["statusReason"] = nv_pn.pn_concept(code_element.pn)
            procedure["code"] = {
                "coding": [nv_pn.pn_coding(code_element.pn)],
                "text": nv_pn.PN_DISPLAY.get(code_element.pn),
            }
        else:
            procedure["status"] = "unknown"
            procedure["code"] = common.absent_reason_concept(code_element)

        prior = group.first("eProcedures.02")
        if prior is not None and prior.has_value and prior.value == common.YES:
            procedure.setdefault("extension", []).append(
                {"url": PRIOR_CARE_EXT, "valueBoolean": True}
            )

        success = group.first("eProcedures.06")
        if success is not None and success.has_value:
            procedure["outcome"] = conceptmaps.dual_code("eProcedures.06", success.value)

        complications = []
        for complication in group.all("eProcedures.07"):
            if complication.has_value:
                # NEMSIS-coded (3907xxx) in 3.5.0 — XSD-verified, not SNOMED.
                complications.append(
                    conceptmaps.dual_code("eProcedures.07", complication.value)
                )
            elif complication.pn == nv_pn.PN_NONE_REPORTED:
                complications.append(nv_pn.pn_concept(complication.pn))
        if complications:
            procedure["complication"] = complications

        body_site = group.first("eProcedures.13")
        if body_site is not None and body_site.has_value:
            procedure["bodySite"] = [conceptmaps.dual_code("eProcedures.13", body_site.value)]

        performers = []
        role = group.first("eProcedures.10")  # read unconditionally: role can
        # be recorded (or NV) even when no crew id is documented
        for crew in group.all("eProcedures.09"):
            if not crew.has_value:
                continue
            practitioner_id = ensure_practitioner(ctx, crew.value)
            performer: dict = {"actor": {"reference": f"Practitioner/{practitioner_id}"}}
            if role is not None and role.has_value:
                performer["function"] = conceptmaps.dual_code("eProcedures.10", role.value)
            performers.append(performer)
        if performers:
            procedure["performer"] = performers

        common.claim_profiles(procedure, "us-core-procedure")
        ctx.add(procedure)
        out.append(procedure)
        _part_of_observation(
            ctx, group, "eProcedures.05", "Number of Procedure Attempts", procedure, "integer"
        )
        _part_of_observation(
            ctx, group, "eProcedures.08", "Response to Procedure", procedure, "code"
        )
    return out
