"""Typed intermediate model for a parsed NEMSIS 3.5 document.

Design (Architecture §5.2): a normalized model in which NV/PN attributes and
xsi:nil are FIRST-CLASS fields. Nil elements are never collapsed here — a
converter that treats xsi:nil as "skip" silently destroys pertinent negatives.

The model is deliberately generic (elements keyed by their NEMSIS element id,
e.g. "eVitals.06") rather than one class per element: NEMSIS has 600+ national
elements and the mapping layer addresses them by id, exactly as the S2T
workbook does.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NemsisElement:
    """One leaf element occurrence, with its negative-value semantics intact."""

    element_id: str  # e.g. "eVitals.06"
    value: str | None  # text content; None when xsi:nil
    nil: bool = False  # xsi:nil="true" present
    nv: str | None = None  # Not-Value attribute (7701xxx)
    pn: str | None = None  # Pertinent-Negative attribute (8801xxx)
    correlation_id: str | None = None  # within-document linking token ONLY
    attributes: dict[str, str] = field(default_factory=dict)  # other XML attrs

    @property
    def has_value(self) -> bool:
        return not self.nil and self.value is not None and self.value != ""

    @property
    def is_not_value(self) -> bool:
        return self.nv is not None

    @property
    def is_pertinent_negative(self) -> bool:
        return self.pn is not None


@dataclass
class NemsisGroup:
    """A (possibly repeating) group instance, e.g. one eVitals.VitalGroup.

    `elements` holds the group's direct leaf elements; `groups` holds nested
    group instances in document order (e.g. BloodPressureGroup inside a
    VitalGroup). Lookups recurse into nested groups so callers can address
    "eVitals.06" on the VitalGroup without knowing the XSD nesting.
    """

    tag: str  # e.g. "eVitals.VitalGroup"
    index: int = 0  # 0-based position among same-tag siblings
    correlation_id: str | None = None
    uuid: str | None = None  # NEMSIS UUID attribute if present
    elements: dict[str, list[NemsisElement]] = field(default_factory=dict)
    groups: list["NemsisGroup"] = field(default_factory=list)
    # Consumption tracker for the never-silently-drop coverage sweep: every
    # element id looked up through this group is recorded here, and the sweep
    # flags anything present in the source that no mapper ever asked for.
    tracker: set[str] | None = field(default=None, repr=False, compare=False)

    def attach_tracker(self, tracker: set[str]) -> None:
        self.tracker = tracker
        for g in self.groups:
            g.attach_tracker(tracker)

    def add(self, element: NemsisElement) -> None:
        self.elements.setdefault(element.element_id, []).append(element)

    def all(self, element_id: str) -> list[NemsisElement]:
        if self.tracker is not None:
            self.tracker.add(element_id)
        found = list(self.elements.get(element_id, []))
        for g in self.groups:
            found.extend(g.all(element_id))
        return found

    def first(self, element_id: str) -> NemsisElement | None:
        found = self.all(element_id)
        return found[0] if found else None

    def value(self, element_id: str) -> str | None:
        el = self.first(element_id)
        return el.value if el is not None and el.has_value else None

    def subgroups(self, tag: str) -> list["NemsisGroup"]:
        found = [g for g in self.groups if g.tag == tag]
        for g in self.groups:
            found.extend(g.subgroups(tag))
        return found

    def element_ids(self) -> set[str]:
        ids = set(self.elements)
        for g in self.groups:
            ids |= g.element_ids()
        return ids


@dataclass
class PatientCareReport:
    """One PatientCareReport, sections keyed by name ("eRecord", "eVitals", ...)."""

    sections: dict[str, NemsisGroup] = field(default_factory=dict)
    uuid: str | None = None  # UUID attribute on the PatientCareReport node

    def attach_tracker(self, tracker: set[str]) -> None:
        for section in self.sections.values():
            section.attach_tracker(tracker)

    def element_ids(self) -> set[str]:
        """Every element id present anywhere in this PCR."""
        ids: set[str] = set()
        for section in self.sections.values():
            ids |= section.element_ids()
        return ids

    def section(self, name: str) -> NemsisGroup | None:
        return self.sections.get(name)

    def all(self, element_id: str) -> list[NemsisElement]:
        sect = self.sections.get(element_id.split(".")[0])
        return sect.all(element_id) if sect else []

    def first(self, element_id: str) -> NemsisElement | None:
        found = self.all(element_id)
        return found[0] if found else None

    def value(self, element_id: str) -> str | None:
        el = self.first(element_id)
        return el.value if el is not None and el.has_value else None

    def groups(self, section: str, tag: str) -> list[NemsisGroup]:
        sect = self.sections.get(section)
        return sect.subgroups(tag) if sect else []

    @property
    def pcr_number(self) -> str | None:
        return self.value("eRecord.01")


@dataclass
class DemographicHeader:
    """The Header/DemographicGroup: dAgency (+ dPersonnel etc. when present)."""

    agency: NemsisGroup = field(default_factory=lambda: NemsisGroup("DemographicGroup"))

    def value(self, element_id: str) -> str | None:
        return self.agency.value(element_id)

    def first(self, element_id: str) -> NemsisElement | None:
        return self.agency.first(element_id)


@dataclass
class EMSDataSet:
    """A parsed EMSDataSet document: header + one or more PCRs."""

    header: DemographicHeader
    reports: list[PatientCareReport] = field(default_factory=list)
    nemsis_version: str | None = None  # detected source version (ADR-007)
