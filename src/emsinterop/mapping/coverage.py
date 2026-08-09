"""Coverage sweep — enforcement of the never-silently-drop hard rule.

The model records every element id a mapper looks up (MappingContext.consumed).
After all mappers run, this sweep diffs the element ids actually present in the
source PCR against that set and logs every leftover in the conversion issue
log: DEFERRED (information) where the S2T workbook intentionally defers the
panel, UNMAPPED (warning) otherwise. Nothing disappears without a ledger entry.
"""

from __future__ import annotations

from ..issues import Disposition
from ..terminology import registry
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
    if element_id == "ePatient.13":
        # Deprecated in 3.5.0 in favour of ePatient.25 Sex (ADR-007). Consumed
        # only as a legacy fallback, so it lands here whenever .25 is present.
        return (
            Disposition.DEFERRED,
            "deprecated in NEMSIS 3.5.0; superseded by ePatient.25 Sex "
            "(read only as a legacy fallback when .25 is absent)",
            "information",
        )
    if not registry.is_national(element_id):
        # State/local element. The project maps the NATIONAL dataset; these are
        # out of scope by design, not coverage gaps. Still ledgered — the
        # never-silently-drop rule is about visibility, not about pretending
        # every state extension is a defect.
        return (
            Disposition.DEFERRED,
            "state/local element (NEMSIS national=No) — outside the national "
            "dataset this project maps",
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
