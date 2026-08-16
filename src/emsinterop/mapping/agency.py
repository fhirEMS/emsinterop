"""dAgency (Header/DemographicGroup) -> Organization.

The only IG-anchored mapping in mPSC. The EMSDataSet header carries only
dAgency.01/.02/.04 (the full roster lives in the DEMDataSet); the Organization
is a cross-PCR shared entity keyed by agency number (ADR-004).
"""

from __future__ import annotations

from ..issues import Disposition
from ..terminology import systems
from . import common
from .context import MappingContext


def map_agency(ctx: MappingContext) -> dict | None:
    state_id = ctx.header.value("dAgency.01")
    number = ctx.header.value("dAgency.02")
    state = ctx.header.value("dAgency.04")
    if not (state_id or number):
        ctx.log("dAgency", Disposition.INVALID, "no agency identifiers in header", "error")
        return None

    org: dict = {
        "resourceType": "Organization",
        "id": ctx.shared_rid("Organization", state_id, number),
        "active": True,
        "identifier": [],
        "type": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/organization-type",
                        "code": "prov",
                        "display": "Healthcare Provider",
                    }
                ]
            }
        ],
    }
    if state_id:
        org["identifier"].append(common.identifier(systems.AGENCY_STATE_ID, state_id))
    if number:
        org["identifier"].append(common.identifier(systems.AGENCY_NUMBER, number))
    if state:
        org["address"] = [{"state": state, "country": "US"}]

    # US Core Organization requires a name; the EMSDataSet header doesn't carry
    # dAgency.03 (DEMDataSet only). A deployment can supply names via
    # MappingContext.agency_names; without one, don't fabricate — emit a
    # data-absent-reason on the name primitive and skip the US Core claim
    # (base-FHIR-valid, honestly non-conformant until the name arrives).
    name = ctx.agency_names.get(number or "") or ctx.agency_names.get(state_id or "")
    if name:
        org["name"] = name
        common.claim_profiles(org, "us-core-organization")
    else:
        ctx.log(
            "dAgency.03",
            Disposition.SEEDED,
            "agency name unavailable in EMSDataSet header (DEMDataSet only); "
            "Organization.name absent and US Core claim withheld — supply via agency_names config",
            "information",
        )
        org["_name"] = {
            "extension": [
                {"url": systems.DATA_ABSENT_REASON_EXT, "valueCode": "unsupported"}
            ]
        }

    ctx.organization_id = org["id"]
    # Agency telecom/address from the DEM roster (dContact). Same rule as the
    # name: supply it or leave it absent.
    contact = ctx.agency_contact
    if contact.get("phone"):
        org["telecom"] = [{"system": "phone", "value": contact["phone"], "use": "work"}]
    address = {}
    for key in ("line", "city", "state", "postalCode"):
        translated = common.address_field(key, contact.get(key), ctx.city_gazetteer)
        if translated:
            address[translated[0]] = translated[1]
    gnis = common.city_gnis_extension(contact.get("city"))
    if gnis:
        address.setdefault("extension", []).append(gnis)
    if address:
        org["address"] = [{"use": "work", **address}]
    return ctx.add(org)
