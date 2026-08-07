"""The outcome payload extracted from a hospital discharge event."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OutcomeRecord:
    sending_facility: str = ""
    patient_class: str = ""  # E = emergency (ED disposition), I = inpatient
    family_name: str = ""
    given_name: str = ""
    birth_date: str = ""  # YYYYMMDD
    identifiers: list[str] = field(default_factory=list)
    visit_number: str = ""
    discharge_status: str = ""  # NUBC — the eOutcome.01/.02 vocabulary
    admit_time: str | None = None
    discharge_time: str | None = None
    diagnoses: list[str] = field(default_factory=list)  # ICD-10-CM
