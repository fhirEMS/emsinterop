"""The outcome loop (Phase 6, inbound half): hospital ADT^A03 discharge
messages -> matched PCR -> NEMSIS eOutcome write-back.

Conservative by default: a candidate links only when EVERY strong signal
agrees (identity + time window + facility); anything partial lands in review —
wrong-patient outcome write-back is the failure mode this design refuses.
"""

from .fhir import is_discharge_summary, outcome_record_from_fhir
from .hl7v2 import outcome_record, parse_adt
from .matching import MatchVerdict, score_match
from .records import OutcomeRecord
from .writeback import apply_outcome

__all__ = [
    "parse_adt", "outcome_record", "outcome_record_from_fhir",
    "is_discharge_summary", "OutcomeRecord", "score_match", "MatchVerdict",
    "apply_outcome",
]
