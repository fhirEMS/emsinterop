"""EMS-course operational panel: eDispatch / eScene facts / eDisposition
course elements / eProtocols -> Observations; prearrival alert -> Communication.

These are the operational "what happened on this run" elements the workbook
routes to the proposed EMS Course section. Valued elements become coded
Observations; NV structural filler is read (consumed/accounted) and represented
at section level, not as per-element noise.
"""

from __future__ import annotations

from ..terminology import conceptmaps, registry, systems
from . import common
from .context import MappingContext

PREARRIVAL_NO_ALERT = "4224001"

_SCENE_ELEMENTS = ["eScene.01", "eScene.05", "eScene.06", "eScene.07", "eScene.08", "eScene.10"]
_DISPATCH_ELEMENTS = ["eDispatch.02", "eDispatch.05"]
_DISPOSITION_ELEMENTS = [
    "eDisposition.11",  # number transported
    "eDisposition.17",  # transport mode from scene
    "eDisposition.18",  # additional transport mode descriptors
    "eDisposition.19",  # acuity on release
    "eDisposition.20",  # reason for choosing destination
    "eDisposition.22",  # hospital in-patient destination
    "eDisposition.23",  # hospital capability
    "eDisposition.26",  # disposition instructions
    "eDisposition.28",  # patient evaluation/care
    "eDisposition.29",  # crew disposition
    "eDisposition.31",  # reason for refusal/release
]


def _prearrival_alert(ctx: MappingContext) -> dict | None:
    """eDisposition.24/.25 -> Communication (destination team activation)."""
    alert = ctx.pcr.first("eDisposition.24")
    sent = ctx.pcr.first("eDisposition.25")
    if alert is None or not (alert.has_value or alert.nv or alert.pn):
        return None
    communication: dict = {
        "resourceType": "Communication",
        "id": ctx.rid("Communication", "prearrival-alert"),
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
        "category": [
            {
                "coding": [{"system": systems.NEMSIS, "code": "eDisposition.24"}],
                "text": registry.element_name("eDisposition.24")
                or "Destination Team Pre-Arrival Alert or Activation",
            }
        ],
    }
    if alert.has_value and alert.value != PREARRIVAL_NO_ALERT:
        communication["status"] = "completed"
        communication["reasonCode"] = [
            conceptmaps.dual_code("eDisposition.24", alert.value)
        ]
        if sent is not None and sent.has_value:
            communication["sent"] = sent.value
    elif alert.has_value:  # explicit "No" — the negative is preserved
        communication["status"] = "not-done"
        communication["statusReason"] = conceptmaps.dual_code(
            "eDisposition.24", alert.value
        )
    else:
        communication["status"] = "unknown"
    return ctx.add(communication)


def map_course(ctx: MappingContext) -> list[dict]:
    out: list[dict] = []

    for element_id in _DISPATCH_ELEMENTS + _SCENE_ELEMENTS + _DISPOSITION_ELEMENTS:
        for occurrence, element in enumerate(ctx.pcr.all(element_id)):
            created = common.course_observation(ctx, element, f"{element_id}-{occurrence}")
            if created is not None:
                out.append(created)

    alert = _prearrival_alert(ctx)
    if alert is not None:
        out.append(alert)

    # eProtocols: one Observation per ProtocolGroup; age category as component.
    for group in ctx.pcr.groups("eProtocols", "eProtocols.ProtocolGroup"):
        protocol = group.first("eProtocols.01")
        if protocol is None or not (protocol.has_value or protocol.nv):
            continue
        obs: dict = {
            "resourceType": "Observation",
            "id": ctx.rid("Observation", "eProtocols", group.index),
            "status": "final",
            "category": [
                {"coding": [{"system": systems.OBSERVATION_CATEGORY, "code": "survey"}]}
            ],
            "code": {
                "coding": [{"system": systems.NEMSIS, "code": "eProtocols.01"}],
                "text": "Protocols Used",
            },
            "subject": ctx.patient_ref(),
            "encounter": ctx.encounter_ref(),
        }
        if protocol.has_value:
            obs["valueCodeableConcept"] = conceptmaps.dual_code(
                "eProtocols.01", protocol.value
            )
        else:
            obs["dataAbsentReason"] = common.absent_reason_concept(protocol)
        age_category = group.first("eProtocols.02")
        if age_category is not None and age_category.has_value:
            obs["component"] = [
                {
                    "code": {
                        "coding": [{"system": systems.NEMSIS, "code": "eProtocols.02"}],
                        "text": "Protocol Age Category",
                    },
                    "valueCodeableConcept": conceptmaps.dual_code(
                        "eProtocols.02", age_category.value
                    ),
                }
            ]
        out.append(ctx.add(obs))
    return out
