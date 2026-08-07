"""Coverage sweep — enforcement of the never-silently-drop hard rule.

The model records every element id a mapper looks up (MappingContext.consumed).
After all mappers run, this sweep diffs the element ids actually present in the
source PCR against that set and logs every leftover in the conversion issue
log: DEFERRED (information) where the S2T workbook intentionally defers the
panel, UNMAPPED (warning) otherwise. Nothing disappears without a ledger entry.
"""

from __future__ import annotations

from ..issues import Disposition
from .context import MappingContext

# Workbook-sanctioned deferrals (docs/02, Coverage_Matrix + panel tabs).
_DEFERRED_SECTIONS = {
    "eOutcome": "outcome loop deferred to external QORH/QORE profile (workbook: Deferred; roadmap Phase 6)",
}

# eInjury.11-.29 = ACN telematics: low field prevalence, deferred to CR/attachment.
_ACN_RANGE = {f"eInjury.{n:02d}" for n in range(11, 30)}


def _classify(element_id: str) -> tuple[Disposition, str, str]:
    section = element_id.split(".")[0]
    if section in _DEFERRED_SECTIONS:
        return Disposition.DEFERRED, _DEFERRED_SECTIONS[section], "information"
    if element_id in _ACN_RANGE:
        return (
            Disposition.DEFERRED,
            "ACN telematics deferred (workbook: Deferred; carried in CR/attachment later)",
            "information",
        )
    if section == "ePayment" and element_id != "ePayment.01":
        return (
            Disposition.DEFERRED,
            "billing detail deferred (workbook: ePayment mostly Deferred)",
            "information",
        )
    return (
        Disposition.UNMAPPED,
        "element present in source but not consumed by any mapper",
        "warning",
    )


def sweep(ctx: MappingContext) -> list[str]:
    """Log every present-but-unconsumed element; returns the flagged ids."""
    unaccounted = sorted(ctx.pcr.element_ids() - ctx.consumed)
    for element_id in unaccounted:
        disposition, reason, severity = _classify(element_id)
        ctx.log(element_id, disposition, reason, severity)
    return unaccounted
