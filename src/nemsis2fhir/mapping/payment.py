"""ePayment.01 -> Coverage (workbook: Mapped; the rest of ePayment is deferred
billing detail, ledgered by the coverage sweep)."""

from __future__ import annotations

from ..terminology import conceptmaps, systems
from . import common
from .context import MappingContext


def map_payment(ctx: MappingContext) -> dict | None:
    method = ctx.pcr.first("ePayment.01")
    if method is None or not method.has_value:
        return None  # NV: consumed by the read; optional Payers section stays empty
    coverage: dict = {
        "resourceType": "Coverage",
        "id": ctx.rid("Coverage"),
        "status": "active",
        "type": conceptmaps.dual_code("ePayment.01", method.value),
        "relationship": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/subscriber-relationship",
                    "code": "self",
                }
            ]
        },
        "beneficiary": ctx.patient_ref(),
        "payor": [
            {
                "extension": [
                    {
                        "url": systems.DATA_ABSENT_REASON_EXT,
                        "valueCode": "unknown",
                    }
                ]
            }
        ],
    }
    # us-core-coverage requires a member id / subscriberId (us-core-15), which
    # NEMSIS billing detail (deferred) doesn't carry — no US Core claim until a
    # payer feed supplies it. The resource remains base-R4 valid.
    return ctx.add(coverage)
