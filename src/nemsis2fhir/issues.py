"""Conversion issue log — the never-silently-drop ledger (Architecture §8).

Every unmapped or invalid element lands here with element id, PCR id, reason,
and disposition. This log is the feedback loop into the S2T workbook's gap
register, and is reconciled against fhirEngine's dead-letter downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Disposition(str, Enum):
    MAPPED = "mapped"
    SEEDED = "seeded"
    DEFERRED = "deferred"
    UNMAPPED = "unmapped"
    INVALID = "invalid"


@dataclass(frozen=True)
class ConversionIssue:
    pcr_number: str | None
    element_id: str
    disposition: Disposition
    reason: str
    severity: str = "warning"  # information | warning | error

    # PHI hygiene: element ids, codes, and PCR ids only — never values.


@dataclass
class IssueLog:
    issues: list[ConversionIssue] = field(default_factory=list)

    def add(
        self,
        pcr_number: str | None,
        element_id: str,
        disposition: Disposition,
        reason: str,
        severity: str = "warning",
    ) -> None:
        self.issues.append(
            ConversionIssue(pcr_number, element_id, disposition, reason, severity)
        )

    def by_disposition(self, disposition: Disposition) -> list[ConversionIssue]:
        return [i for i in self.issues if i.disposition == disposition]

    def __len__(self) -> int:
        return len(self.issues)
