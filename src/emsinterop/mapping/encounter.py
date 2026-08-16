"""eResponse / eDispatch / eTimes / eScene / eDisposition -> Encounter (the spine).

One Encounter per PatientCareReport (ADR-004); every clinical resource
references it. Scene and destination become Location resources; the finer
eTimes timestamps become a timeline Observation cluster so nothing is dropped.
"""

from __future__ import annotations

from ..issues import Disposition
from ..terminology import conceptmaps, registry, systems
from . import common
from .context import MappingContext

_CANCELLED_UNIT_DISPOSITIONS = {"4227003", "4227005"}  # cancelled on scene / prior to arrival
_TIMELINE_ELEMENTS = [
    "eTimes.01",  # PSAP call
    "eTimes.02",  # dispatch notified
    "eTimes.03",  # unit notified
    "eTimes.04",  # dispatch acknowledged
    "eTimes.05",  # en route
    "eTimes.06",  # arrived on scene
    "eTimes.07",  # arrived at patient
    "eTimes.08",  # transfer of EMS patient care
    "eTimes.09",  # left scene
    "eTimes.10",  # arrival at landing zone
    "eTimes.11",  # arrived at destination
    "eTimes.12",  # transfer of care
    "eTimes.13",  # back in service
    "eTimes.14",  # transport arrived
    "eTimes.15",  # canceled
    "eTimes.16",  # back at home location
    "eTimes.17",  # declared dead
]
_RESPONSE_DELAY_ELEMENTS = [
    "eResponse.08",  # dispatch delay
    "eResponse.09",  # response delay
    "eResponse.10",  # scene delay
    "eResponse.11",  # transport delay
    "eResponse.12",  # turnaround delay
    "eResponse.24",  # additional response mode descriptors
]


def _scene_location(ctx: MappingContext) -> dict | None:
    scene = ctx.pcr.section("eScene")
    if scene is None:
        return None
    details: dict = {}
    loc_type = scene.first("eScene.09")
    if loc_type is not None and loc_type.has_value:
        details["type"] = [conceptmaps.dual_code("eScene.09", loc_type.value)]
    address: dict = {}
    for element_id, key in [
        ("eScene.15", "line"),
        ("eScene.17", "city"),
        ("eScene.18", "state"),
        ("eScene.19", "postalCode"),
        ("eScene.21", "district"),
        ("eScene.22", "country"),
    ]:
        el = scene.first(element_id)
        if el is not None and el.has_value:
            if key == "line":
                address["line"] = [el.value]
                continue
            # NEMSIS codes places; FHIR names them. The code never goes into a
            # name field — see common.address_field and the city-is-a-gnis-code
            # gap. The GNIS id is preserved as an extension so nothing is lost.
            if key == "city":
                extension = common.city_gnis_extension(el.value)
                if extension:
                    address.setdefault("extension", []).append(extension)
            translated = common.address_field(key, el.value, ctx.city_gazetteer)
            if translated:
                address[translated[0]] = translated[1]
    if address:
        details["address"] = address
    gps = scene.first("eScene.11")
    if gps is not None and gps.has_value and "," in gps.value:
        lat, lon = gps.value.split(",", 1)
        try:
            details["position"] = {"latitude": float(lat), "longitude": float(lon)}
        except ValueError:
            ctx.log("eScene.11", Disposition.INVALID, "unparseable GPS coordinate")
    facility = scene.first("eScene.13")  # incident facility (e.g. sending hospital)
    if not details and not (facility is not None and facility.has_value):
        return None
    location: dict = {
        "resourceType": "Location",
        "id": ctx.rid("Location", "scene"),
        "name": (
            facility.value
            if facility is not None and facility.has_value
            else "EMS scene"
        ),
        **details,
    }
    return ctx.add(location)


def _vehicle_location(ctx: MappingContext) -> dict | None:
    """eResponse.13/.14 -> the EMS unit as a Location (mode=kind vehicle)."""
    unit = ctx.pcr.first("eResponse.13")
    call_sign = ctx.pcr.first("eResponse.14")
    has_unit = unit is not None and unit.has_value
    has_sign = call_sign is not None and call_sign.has_value
    if not (has_unit or has_sign):
        return None
    location: dict = {
        "resourceType": "Location",
        "id": ctx.rid("Location", "vehicle"),
        "physicalType": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/location-physical-type",
                    "code": "ve",
                    "display": "Vehicle",
                }
            ]
        },
    }
    if has_sign:
        location["name"] = call_sign.value
    if has_unit:
        location["identifier"] = [
            common.identifier("urn:nemsis:identifier:unit-number", unit.value)
        ]
        if not has_sign:
            location["name"] = unit.value
    return ctx.add(location)


def _destination_location(ctx: MappingContext) -> dict | None:
    disp = ctx.pcr.section("eDisposition")
    if disp is None:
        return None
    # Read the whole destination group up front (required-nillable address
    # elements must be consumed even on no-transport runs), then decide.
    name = disp.first("eDisposition.01")
    code = disp.first("eDisposition.02")
    dest_type = disp.first("eDisposition.21")
    address: dict = {}
    for element_id, key in [
        ("eDisposition.03", "line"),
        ("eDisposition.04", "city"),
        ("eDisposition.05", "state"),
        ("eDisposition.06", "district"),
        ("eDisposition.07", "postalCode"),
    ]:
        el = disp.first(element_id)
        if el is not None and el.has_value:
            if key == "line":
                address["line"] = [el.value]
                continue
            # NEMSIS codes places; FHIR names them. The code never goes into a
            # name field — see common.address_field and the city-is-a-gnis-code
            # gap. The GNIS id is preserved as an extension so nothing is lost.
            if key == "city":
                extension = common.city_gnis_extension(el.value)
                if extension:
                    address.setdefault("extension", []).append(extension)
            translated = common.address_field(key, el.value, ctx.city_gazetteer)
            if translated:
                address[translated[0]] = translated[1]
    if (name is None or not name.has_value) and (code is None or not code.has_value):
        return None
    location: dict = {
        "resourceType": "Location",
        "id": ctx.rid("Location", "destination"),
    }
    if name is not None and name.has_value:
        location["name"] = name.value
    if code is not None and code.has_value:
        location["identifier"] = [
            common.identifier("urn:nemsis:identifier:destination-code", code.value)
        ]
    if dest_type is not None and dest_type.has_value:
        location["type"] = [conceptmaps.dual_code("eDisposition.21", dest_type.value)]
    if address:
        location["address"] = address
    return ctx.add(location)


def _timeline_observations(ctx: MappingContext) -> None:
    for element_id in _TIMELINE_ELEMENTS:
        el = ctx.pcr.first(element_id)
        if el is None or not el.has_value:
            continue
        ctx.add(
            {
                "resourceType": "Observation",
                "id": ctx.rid("Observation", element_id),
                "status": "final",
                "category": [
                    {
                        "coding": [
                            {"system": systems.OBSERVATION_CATEGORY, "code": "survey"}
                        ]
                    }
                ],
                "code": {
                    "coding": [{"system": systems.NEMSIS, "code": element_id}],
                    "text": registry.element_name(element_id) or element_id,
                },
                "subject": ctx.patient_ref(),
                "encounter": ctx.encounter_ref(),
                "valueDateTime": common.fhir_datetime(el.value),
            }
        )


def map_encounter(ctx: MappingContext) -> dict:
    pcr = ctx.pcr
    encounter: dict = {
        "resourceType": "Encounter",
        "id": ctx.rid("Encounter"),
        "class": {
            "system": systems.V3_ACT_CODE,
            "code": "FLD",
            "display": "field",
        },
        "subject": ctx.patient_ref(),
    }
    ctx.encounter_id = encounter["id"]

    # status from unit disposition (eDisposition.27)
    unit_disp = pcr.first("eDisposition.27")
    if unit_disp is not None and unit_disp.has_value:
        encounter["status"] = (
            "cancelled" if unit_disp.value in _CANCELLED_UNIT_DISPOSITIONS else "finished"
        )
    else:
        encounter["status"] = "finished"

    identifiers = []
    incident = pcr.first("eResponse.03")
    if incident is not None and incident.has_value:
        identifiers.append(common.identifier(systems.INCIDENT_ID, incident.value))
    response = pcr.first("eResponse.04")
    if response is not None and response.has_value:
        identifiers.append(common.identifier(systems.RESPONSE_ID, response.value))
    pcr_num = pcr.first("eRecord.01")
    if pcr_num is not None and pcr_num.has_value:
        identifiers.append(common.identifier(systems.PCR_ID, pcr_num.value))
    if identifiers:
        encounter["identifier"] = identifiers

    types = []
    service = pcr.first("eResponse.05")
    if service is not None and service.has_value:
        types.append(conceptmaps.dual_code("eResponse.05", service.value))
    capability = pcr.first("eResponse.07")
    if capability is not None and capability.has_value:
        types.append(conceptmaps.dual_code("eResponse.07", capability.value))
    transport_method = pcr.first("eDisposition.16")
    if transport_method is not None and transport_method.has_value:
        types.append(conceptmaps.dual_code("eDisposition.16", transport_method.value))
    level_of_care = pcr.first("eDisposition.32")
    if level_of_care is not None and level_of_care.has_value:
        types.append(conceptmaps.dual_code("eDisposition.32", level_of_care.value))
    if types:
        encounter["type"] = types

    priority = pcr.first("eResponse.23")
    if priority is not None and priority.has_value:
        encounter["priority"] = conceptmaps.dual_code(
            "eResponse.23", priority.value, "cm-nemsis-priority"
        )

    reasons = []
    reason = pcr.first("eDispatch.01")
    if reason is not None and reason.has_value:
        reasons.append(conceptmaps.dual_code("eDispatch.01", reason.value))
    # Interfacility transfer justification/reason (RIPT use case).
    for element_id in ("eSituation.19", "eSituation.20"):
        transfer = pcr.first(element_id)
        if transfer is not None and transfer.has_value:
            if element_id == "eSituation.19":  # free-text justification
                reasons.append({"text": transfer.value})
            else:
                reasons.append(conceptmaps.dual_code(element_id, transfer.value))
    if reasons:
        encounter["reasonCode"] = reasons

    period: dict = {}
    start = pcr.first("eTimes.06") or pcr.first("eTimes.03")
    if start is not None and start.has_value:
        period["start"] = common.fhir_datetime(start.value)
    end = pcr.first("eTimes.12") or pcr.first("eTimes.11")
    if end is not None and end.has_value:
        period["end"] = common.fhir_datetime(end.value)
    if period:
        encounter["period"] = period
        ctx.encounter_period = period

    # eResponse.01 ties the Encounter to the responding agency; the Organization
    # itself comes from the header. Cross-check the two, surfacing a mismatch.
    agency = pcr.first("eResponse.01")
    header_agency = ctx.header.value("dAgency.02")
    if (
        agency is not None
        and agency.has_value
        and header_agency
        and agency.value != header_agency
    ):
        ctx.log(
            "eResponse.01",
            Disposition.INVALID,
            f"responding agency differs from header dAgency.02 ({agency.value} != {header_agency})",
        )
    if ctx.organization_id:
        encounter["serviceProvider"] = {"reference": f"Organization/{ctx.organization_id}"}

    hospitalization: dict = {}
    transport_disp = pcr.first("eDisposition.30")
    if transport_disp is not None and transport_disp.has_value:
        hospitalization["dischargeDisposition"] = conceptmaps.dual_code(
            "eDisposition.30", transport_disp.value
        )

    scene = _scene_location(ctx)
    locations = []
    if scene is not None:
        locations.append({"location": ctx.ref(scene), "status": "completed"})
    vehicle = _vehicle_location(ctx)
    if vehicle is not None:
        locations.append({"location": ctx.ref(vehicle), "status": "active"})
    destination = _destination_location(ctx)
    if destination is not None:
        hospitalization["destination"] = ctx.ref(destination)
    if hospitalization:
        encounter["hospitalization"] = hospitalization
    if locations:
        encounter["location"] = locations

    common.claim_profiles(encounter, "us-core-encounter")
    ctx.add(encounter)
    _timeline_observations(ctx)

    # Response delays / additional descriptors: operational, valued -> course
    # Observation (NV filler is consumed and represented by its absence).
    for element_id in _RESPONSE_DELAY_ELEMENTS:
        for occurrence, element in enumerate(pcr.all(element_id)):
            common.course_observation(ctx, element, f"{element_id}-{occurrence}")
    return encounter
