"""eCrew -> Practitioner + PractitionerRole.

Practitioner is a cross-PCR shared entity keyed by (agency, personnel id) so
eMedications.09 / eProcedures.09 crew references resolve to the same resource
across submissions (ADR-004). PractitionerRole is PCR-scoped (role on this
encounter).
"""

from __future__ import annotations

from ..terminology import conceptmaps, systems
from . import common
from .context import MappingContext


def practitioner_id_for(ctx: MappingContext, crew_member_id: str) -> str:
    agency = ctx.header.value("dAgency.02")
    return ctx.shared_rid("Practitioner", agency, crew_member_id)


def ensure_practitioner(ctx: MappingContext, crew_member_id: str) -> str:
    """Create the shared Practitioner for a crew id if not already in the graph."""
    pid = practitioner_id_for(ctx, crew_member_id)
    if not any(r["id"] == pid and r["resourceType"] == "Practitioner" for r in ctx.resources):
        practitioner = {
            "resourceType": "Practitioner",
            "id": pid,
            "identifier": [common.identifier(systems.PERSONNEL_ID, crew_member_id)],
        }
        # The PCR identifies crew by state licensure number and carries no
        # names; the DEM roster has them. Same shape as the agency name, and
        # the same rule: supply it or leave it absent, never fabricate.
        entry = ctx.personnel_names.get(crew_member_id) or {}
        if entry.get("family") or entry.get("given"):
            practitioner["name"] = [{
                "use": "official",
                **({"family": entry["family"]} if entry.get("family") else {}),
                **({"given": [entry["given"]]} if entry.get("given") else {}),
            }]
        if entry.get("phone"):
            practitioner["telecom"] = [
                {"system": "phone", "value": entry["phone"], "use": "work"}]
        if entry.get("address"):
            practitioner["address"] = [{"use": "work", **entry["address"]}]
        ctx.add(practitioner)
    return pid


def map_crew(ctx: MappingContext) -> list[dict]:
    roles: list[dict] = []
    section = ctx.pcr.section("eCrew")
    if section is None:
        return roles
    groups = section.subgroups("eCrew.CrewGroup") or [section]
    for index, group in enumerate(groups):
        member = group.first("eCrew.01")
        if member is None or not member.has_value:
            continue
        practitioner_id = ensure_practitioner(ctx, member.value)
        role: dict = {
            "resourceType": "PractitionerRole",
            "id": ctx.rid("PractitionerRole", index),
            "practitioner": {"reference": f"Practitioner/{practitioner_id}"},
        }
        if ctx.organization_id:
            role["organization"] = {"reference": f"Organization/{ctx.organization_id}"}
        codes = []
        level = group.first("eCrew.02")
        if level is not None and level.has_value:
            codes.append(conceptmaps.dual_code("eCrew.02", level.value))
        for response_role in group.all("eCrew.03"):
            if response_role.has_value:
                codes.append(conceptmaps.dual_code("eCrew.03", response_role.value))
        if codes:
            role["code"] = codes
        roles.append(ctx.add(role))
    return roles
