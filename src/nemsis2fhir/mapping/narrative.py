"""eNarrative -> DocumentReference (the free-text PCR narrative).

The narrative also feeds the proposed EMS Narrative Composition section and,
later, Composition.section.text. NV on eNarrative.01 is consumed and
represented by the section's emptyReason.
"""

from __future__ import annotations

import base64

from ..terminology import systems
from . import common
from .context import MappingContext


def map_narrative(ctx: MappingContext) -> dict | None:
    narrative = ctx.pcr.first("eNarrative.01")
    if narrative is None or not narrative.has_value:
        return None
    document: dict = {
        "resourceType": "DocumentReference",
        "id": ctx.rid("DocumentReference", "narrative"),
        "status": "current",
        "type": {
            # US Core requires a note-type code (required binding): LOINC
            # 67796-3 EMS patient care report; NEMSIS element retained.
            "coding": [
                {
                    "system": systems.LOINC,
                    "code": "67796-3",
                    "display": "EMS patient care report",
                },
                {"system": systems.NEMSIS, "code": "eNarrative.01"},
            ],
            "text": "Patient Care Report Narrative",
        },
        "category": [
            {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/us/core/CodeSystem/us-core-documentreference-category",
                        "code": "clinical-note",
                        "display": "Clinical Note",
                    }
                ]
            }
        ],
        "subject": ctx.patient_ref(),
        "context": {"encounter": [ctx.encounter_ref()]},
        "content": [
            {
                "attachment": {
                    "contentType": "text/plain",
                    "data": base64.b64encode(narrative.value.encode()).decode(),
                }
            }
        ],
    }
    common.claim_profiles(document, "us-core-documentreference")
    return ctx.add(document)
