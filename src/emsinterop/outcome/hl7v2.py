"""Minimal HL7 v2 parsing — just enough to read a hospital ADT^A03.

Pipe-delimited ER7 with MSH-2-declared encoding characters; segments split on
\\r (\\n tolerated for files). No repetition/subcomponent semantics beyond what
the outcome extraction needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .records import OutcomeRecord

_UNESCAPES = [("\\F\\", "|"), ("\\S\\", "^"), ("\\R\\", "~"), ("\\T\\", "&"), ("\\E\\", "\\")]


def _unesc(value: str) -> str:
    for escape, char in _UNESCAPES:
        value = value.replace(escape, char)
    return value


def _dtm_to_iso(dtm: str) -> str | None:
    """HL7 DTM -> ISO 8601 (offset preserved when present)."""
    if not dtm:
        return None
    tz = ""
    body = dtm
    for sign in ("+", "-"):
        at = dtm.find(sign, 8)  # offsets appear after the date part
        if at > 0:
            body, tz = dtm[:at], dtm[at:]
            if len(tz) == 5:
                tz = f"{tz[:3]}:{tz[3:]}"
            break
    body = body.ljust(14, "0")[:14]
    return (
        f"{body[0:4]}-{body[4:6]}-{body[6:8]}T{body[8:10]}:{body[10:12]}:{body[12:14]}{tz}"
    )


@dataclass
class Segment:
    name: str
    fields: list[str]

    def field(self, index: int) -> str:
        """1-based HL7 field access (MSH's encoding-chars offset handled)."""
        # MSH-1 IS the field separator, so stored fields start at MSH-2.
        at = index - 1 if self.name != "MSH" else index - 2
        if self.name == "MSH" and index == 1:
            return "|"
        return _unesc(self.fields[at]) if 0 <= at < len(self.fields) else ""

    def component(self, index: int, component: int) -> str:
        parts = self.field(index).split("^")
        return parts[component - 1] if component <= len(parts) else ""


@dataclass
class AdtMessage:
    segments: list[Segment] = field(default_factory=list)

    def first(self, name: str) -> Segment | None:
        return next((s for s in self.segments if s.name == name), None)

    def all(self, name: str) -> list[Segment]:
        return [s for s in self.segments if s.name == name]


def parse_adt(message: str) -> AdtMessage:
    segments = []
    for raw in message.replace("\n", "\r").split("\r"):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split("|")
        segments.append(Segment(name=parts[0], fields=parts[1:]))
    return AdtMessage(segments=segments)


def outcome_record(adt: AdtMessage) -> OutcomeRecord:
    """Extract the eOutcome-relevant payload + matching keys from an A03."""
    msh, pid, pv1 = adt.first("MSH"), adt.first("PID"), adt.first("PV1")
    if pid is None or pv1 is None:
        raise ValueError("ADT message lacks PID/PV1 — not a usable discharge event")
    patient_class = pv1.field(2).upper()[:1]
    diagnoses = [dg1.component(3, 1) for dg1 in adt.all("DG1") if dg1.component(3, 1)]
    return OutcomeRecord(
        sending_facility=msh.field(4) if msh else "",
        patient_class=patient_class,
        family_name=pid.component(5, 1),
        given_name=pid.component(5, 2),
        birth_date=(pid.field(7) or "")[:8],
        identifiers=[part.split("^")[0] for part in pid.field(3).split("~") if part],
        visit_number=pv1.component(19, 1),
        discharge_status=pv1.field(36),
        admit_time=_dtm_to_iso(pv1.field(44)),
        discharge_time=_dtm_to_iso(pv1.field(45)),
        diagnoses=diagnoses,
    )
