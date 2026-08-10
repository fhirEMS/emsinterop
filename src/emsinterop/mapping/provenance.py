"""Provenance for the converted graph (Architecture §5.5a).

One Provenance per PCR targeting every generated resource: source PCR id +
UUID, mapping-ruleset version, software attribution from eRecord.02-.04, agent
= this converter. No PHI beyond what the resources already carry.
"""

from __future__ import annotations

from .. import MAPPING_RULESET_VERSION
from ..terminology import systems
from . import common
from .context import MappingContext


def map_provenance(ctx: MappingContext) -> dict:
    targets = [
        {"reference": f"{r['resourceType']}/{r['id']}"}
        for r in ctx.resources
        if r["resourceType"] != "Provenance"
    ]
    provenance: dict = {
        "resourceType": "Provenance",
        "id": ctx.rid("Provenance"),
        "target": targets,
        "agent": [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                            "code": "assembler",
                        }
                    ]
                },
                "who": {"display": f"emsinterop mapper (ruleset {MAPPING_RULESET_VERSION})"},
            }
        ],
        "entity": [
            {
                "role": "source",
                "what": {
                    "identifier": {
                        "system": systems.PCR_ID,
                        "value": ctx.pcr_number or "unknown",
                    }
                },
            }
        ],
    }
    transfer_of_care = ctx.pcr.first("eTimes.12")
    if transfer_of_care is not None and transfer_of_care.has_value:
        provenance["occurredDateTime"] = common.fhir_datetime(transfer_of_care.value)

    software = [
        ctx.pcr.value("eRecord.02"),
        ctx.pcr.value("eRecord.03"),
        ctx.pcr.value("eRecord.04"),
    ]
    if any(software):
        provenance["agent"].append(
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                            "code": "author",
                        }
                    ]
                },
                "who": {
                    "display": " ".join(s for s in software if s) or "source ePCR software"
                },
            }
        )
    # recorded is stamped at submission time by the caller; deterministic
    # output (golden-corpus diffable) must not embed wall-clock here.
    return ctx.add(provenance)
