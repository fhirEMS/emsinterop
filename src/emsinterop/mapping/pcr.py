"""Per-PCR orchestration: run every panel mapper, then Provenance."""

from __future__ import annotations

from ..model import EMSDataSet, PatientCareReport
from .agency import map_agency
from .arrest import map_arrest
from .context import MappingContext
from .course import map_course
from .coverage import sweep
from .crew import map_crew
from .encounter import map_encounter
from .exam import map_exam
from .history import map_history
from .injury import map_injury
from .medications import map_medications
from .narrative import map_narrative
from .patient import map_patient
from .payment import map_payment
from .procedures import map_procedures
from .provenance import map_provenance
from .situation import map_situation
from .vitals import map_vitals


def map_pcr(
    dataset: EMSDataSet,
    pcr: PatientCareReport,
    agency_names: dict[str, str] | None = None,
    personnel_names: dict[str, dict[str, str]] | None = None,
) -> MappingContext:
    """Map one PatientCareReport to its canonical FHIR resource graph."""
    ctx = MappingContext(
        pcr=pcr,
        header=dataset.header,
        nemsis_version=dataset.nemsis_version,
        agency_names=agency_names or {},
        personnel_names=personnel_names or {},
    )
    map_agency(ctx)
    map_patient(ctx)
    map_encounter(ctx)
    map_crew(ctx)
    map_situation(ctx)
    map_injury(ctx)
    map_arrest(ctx)
    map_history(ctx)
    map_exam(ctx)
    map_vitals(ctx)
    map_medications(ctx)
    map_procedures(ctx)
    map_course(ctx)
    map_payment(ctx)
    map_narrative(ctx)
    map_provenance(ctx)
    sweep(ctx)  # never-silently-drop: ledger everything no mapper consumed
    return ctx


def map_dataset(dataset: EMSDataSet) -> list[MappingContext]:
    return [map_pcr(dataset, pcr) for pcr in dataset.reports]
