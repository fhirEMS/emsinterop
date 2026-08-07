"""Deterministic PCR<->discharge matching — review-first by design.

Three signal groups, each must individually pass for LINKED:
  identity  — family+given (case-insensitive) AND birth date; a shared
              identifier (SSN / agency patient id) also satisfies identity.
  timing    — the hospital admit falls within a window after the EMS
              transfer of care (default 6h; hospitals often register late).
  facility  — the sending facility matches the EMS destination (code or
              name substring), when the PCR recorded a destination.
Anything partial -> REVIEW (a human links it). Nothing auto-links on fewer
than all available signals: wrong-patient outcome write-back is the failure
mode this refuses. Signals the PCR cannot offer (no destination recorded)
count as REVIEW, never as a pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from ..model import PatientCareReport
from .records import OutcomeRecord


class MatchVerdict(str, Enum):
    LINKED = "linked"
    REVIEW = "review"
    NO_MATCH = "no-match"


@dataclass
class MatchResult:
    verdict: MatchVerdict
    signals: dict[str, bool | None]  # None = signal unavailable

    @property
    def linked(self) -> bool:
        return self.verdict == MatchVerdict.LINKED


def _identity(pcr: PatientCareReport, record: OutcomeRecord) -> bool | None:
    shared_ids = {i for i in record.identifiers if i} & {
        v for v in (pcr.value("ePatient.01"), pcr.value("ePatient.12")) if v
    }
    if shared_ids:
        return True
    family, given = pcr.value("ePatient.02"), pcr.value("ePatient.03")
    dob = (pcr.value("ePatient.17") or "").replace("-", "")
    if not (family and given and dob):
        return None
    names_match = (
        family.lower() == record.family_name.lower()
        and given.lower() == record.given_name.lower()
    )
    return names_match and dob == record.birth_date


def _timing(pcr: PatientCareReport, record: OutcomeRecord, window_hours: float) -> bool | None:
    transfer = pcr.value("eTimes.12") or pcr.value("eTimes.11")
    if not transfer or not record.admit_time:
        return None
    try:
        handoff = datetime.fromisoformat(transfer)
        admit = datetime.fromisoformat(record.admit_time)
    except ValueError:
        return None
    delta = admit - handoff
    return timedelta(hours=-1) <= delta <= timedelta(hours=window_hours)


def _facility(pcr: PatientCareReport, record: OutcomeRecord) -> bool | None:
    destination_code = pcr.value("eDisposition.02")
    destination_name = pcr.value("eDisposition.01")
    if not (destination_code or destination_name) or not record.sending_facility:
        return None
    sender = record.sending_facility.lower()
    if destination_code and destination_code.lower() == sender:
        return True
    if destination_name and (
        sender in destination_name.lower() or destination_name.lower() in sender
    ):
        return True
    return False


def score_match(
    pcr: PatientCareReport, record: OutcomeRecord, window_hours: float = 6.0
) -> MatchResult:
    signals = {
        "identity": _identity(pcr, record),
        "timing": _timing(pcr, record, window_hours),
        "facility": _facility(pcr, record),
    }
    if signals["identity"] is False:
        return MatchResult(MatchVerdict.NO_MATCH, signals)
    if all(value is True for value in signals.values()):
        return MatchResult(MatchVerdict.LINKED, signals)
    if signals["timing"] is False and signals["facility"] is False:
        return MatchResult(MatchVerdict.NO_MATCH, signals)
    return MatchResult(MatchVerdict.REVIEW, signals)
