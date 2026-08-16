"""Shared state for one PCR conversion: identity, references, issues, graph."""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import MAPPING_RULESET_VERSION
from ..issues import Disposition, IssueLog
from ..model import DemographicHeader, PatientCareReport
from ..submit import ids

RESOURCE_ID_SYSTEM = "urn:emsinterop:resource-id"


@dataclass
class MappingContext:
    pcr: PatientCareReport
    header: DemographicHeader
    issues: IssueLog = field(default_factory=IssueLog)
    resources: list[dict] = field(default_factory=list)
    nemsis_version: str | None = None

    # Deployment-supplied agency metadata the EMSDataSet header cannot carry
    # (dAgency.03 lives in the DEMDataSet): agency number or state id -> name.
    agency_names: dict[str, str] = field(default_factory=dict)
    #: dPersonnel.23 (state licensure id) -> {"family", "given"}, from the DEM
    #: roster. A PCR names its crew by licensure number only, so without this
    #: every Practitioner is anonymous.
    personnel_names: dict[str, dict[str, str]] = field(default_factory=dict)

    # ids of the spine resources, set as mappers run
    patient_id: str | None = None
    encounter_id: str | None = None
    organization_id: str | None = None
    #: The Encounter.period, once mapped. Vitals/exam use it to bound an
    #: undated measurement to the call it was taken during (see vitals.py).
    encounter_period: dict | None = None

    # Every element id any mapper looks up (recorded automatically by the
    # model's lookup methods). The coverage sweep diffs this against what the
    # source actually contains — the never-silently-drop guarantee.
    consumed: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        agency_number = self.header.value("dAgency.02")
        self._pcr_key = ids.pcr_key(agency_number, self.pcr.pcr_number, self.pcr.uuid)
        self.pcr.attach_tracker(self.consumed)

    @property
    def pcr_number(self) -> str | None:
        return self.pcr.pcr_number

    def rid(self, resource_type: str, *discriminator: str | int | None) -> str:
        """Deterministic id for a PCR-scoped resource."""
        return ids.resource_id(self._pcr_key, resource_type, *discriminator)

    def shared_rid(self, resource_type: str, *business_identifier: str | None) -> str:
        """Deterministic id for a cross-PCR entity keyed by business identifier
        (Organization by agency number, Practitioner by personnel id) so
        repeat submissions reference the same resource (ADR-004)."""
        return ids.resource_id(resource_type, *business_identifier)

    def add(self, resource: dict) -> dict:
        """Register a resource in the graph, stamping the mapping-version tag
        and the deterministic resource-id identifier (the conditional-update
        key for idempotent resubmission — fhirEngine upserts on
        `PUT Type?identifier=...`, preserving client-supplied ids on create)."""
        meta = resource.setdefault("meta", {})
        meta.setdefault("tag", []).append(
            {
                "system": "urn:emsinterop:mapping-ruleset",
                "code": MAPPING_RULESET_VERSION,
            }
        )
        # Provenance has no identifier element in R4 (matched by target instead);
        # Composition.identifier is a single business identifier (the PCR number).
        if resource["resourceType"] not in ("Provenance", "Composition"):
            identifiers = resource.setdefault("identifier", [])
            if not any(i.get("system") == RESOURCE_ID_SYSTEM for i in identifiers):
                identifiers.append(
                    {"system": RESOURCE_ID_SYSTEM, "value": resource["id"]}
                )
        self.resources.append(resource)
        return resource

    def log(
        self,
        element_id: str,
        disposition: Disposition,
        reason: str,
        severity: str = "warning",
    ) -> None:
        self.issues.add(self.pcr_number, element_id, disposition, reason, severity)

    def ref(self, resource: dict | str, resource_type: str | None = None) -> dict:
        if isinstance(resource, dict):
            return {"reference": f"{resource['resourceType']}/{resource['id']}"}
        return {"reference": f"{resource_type}/{resource}"}

    def patient_ref(self) -> dict:
        return {"reference": f"Patient/{self.patient_id}"}

    def encounter_ref(self) -> dict:
        return {"reference": f"Encounter/{self.encounter_id}"}
