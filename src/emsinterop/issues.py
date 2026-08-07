"""Conversion issue log — the never-silently-drop ledger (Architecture §8).

Every unmapped or invalid element lands here with element id, PCR id, reason,
and disposition. This log is the feedback loop into the S2T workbook's gap
register, and is reconciled against fhirEngine's dead-letter downstream.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


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

    def to_dict(self) -> dict:
        data = asdict(self)
        data["disposition"] = self.disposition.value
        return data


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

    def extend(self, issues: list[ConversionIssue]) -> None:
        self.issues.extend(issues)

    def to_dicts(self) -> list[dict]:
        return [i.to_dict() for i in self.issues]

    def write_jsonl(self, path: str | Path) -> int:
        """Append the log to a JSONL file (the persisted gap-register feed);
        returns the number of rows written."""
        rows = self.to_dicts()
        with Path(path).open("a", encoding="utf-8") as sink:
            for row in rows:
                sink.write(json.dumps(row) + "\n")
        return len(rows)

    def __len__(self) -> int:
        return len(self.issues)


def read_jsonl(path: str | Path) -> IssueLog:
    """Load a persisted issue log back into memory."""
    log = IssueLog()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        data["disposition"] = Disposition(data["disposition"])
        log.issues.append(ConversionIssue(**data))
    return log


_SEVERITY = {"fatal": "error", "error": "error", "warning": "warning",
             "information": "information"}


def issues_from_operation_outcome(
    outcome: dict | None, pcr_number: str | None, status_code: int | None = None
) -> list[ConversionIssue]:
    """Fold a fhirEngine rejection into the issue log.

    Transaction bundles are pre-validated and rejected ATOMICALLY by
    fhirEngine — a rejected transaction never reaches its dead-letter table —
    so the OperationOutcome returned at submit time is the only record of the
    failure and must be captured here. element_id carries the FHIRPath
    expression/location of the server issue (not a NEMSIS element id);
    diagnostics are truncated as a PHI-exposure hedge.
    """
    prefix = f"fhirEngine rejected (HTTP {status_code})" if status_code else \
        "fhirEngine rejected"
    issues: list[ConversionIssue] = []
    for item in (outcome or {}).get("issue", []):
        where = (item.get("expression") or item.get("location") or ["transaction"])[0]
        detail = item.get("diagnostics") or (item.get("details") or {}).get("text", "")
        reason = f"{prefix}: {item.get('code', 'unknown')}: {detail[:300]}"
        issues.append(ConversionIssue(
            pcr_number, where, Disposition.INVALID, reason,
            _SEVERITY.get(item.get("severity", "error"), "error"),
        ))
    if not issues:
        issues.append(ConversionIssue(
            pcr_number, "transaction", Disposition.INVALID, prefix, "error"))
    return issues
