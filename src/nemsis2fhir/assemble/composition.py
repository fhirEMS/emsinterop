"""Layer B: mPSC IPS document assembly (thin, swappable projection — ADR-001).

Assembled from the mapper's IN-MEMORY graph, never read back from fhirEngine
(medallion Gold is eventually consistent — hard rule). Every mandatory section
carries entries or an emptyReason (ihe-pcc-comp-1), with the emptyReason
derived from the source panel's NV where one exists.

Sections marked proposed=True are our upstream proposals; the current mPSC
draft defines only Problems / Allergies / Medication Summary / Payers.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..mapping.context import MappingContext
from ..terminology import nv_pn, systems

MPSC_COMPOSITION_TYPE = {
    "coding": [
        {
            "system": systems.LOINC,
            "code": "107903-7",
            "display": "Paramedicine summary of care note",
        }
    ]
}


@dataclass(frozen=True)
class SectionSpec:
    title: str
    loinc: str
    proposed: bool  # True = section we propose upstream, not yet in mPSC draft
    mandatory: bool  # mandatory sections always emitted (entries or emptyReason)
    nv_source: str | None  # element whose NV drives emptyReason


def _has_category(resource: dict, *codes: str) -> bool:
    categories = resource.get("category")
    if not isinstance(categories, list):
        return False
    for category in categories:
        if not isinstance(category, dict):
            continue
        for coding in category.get("coding", []):
            if coding.get("code") in codes:
                return True
    return False


def _is_vital(resource: dict) -> bool:
    return _has_category(resource, "vital-signs")


def _section_resources(ctx: MappingContext, spec: SectionSpec) -> list[dict]:
    resources = ctx.resources
    if spec.loinc == "11450-4":  # Problems
        return [r for r in resources if r["resourceType"] == "Condition"]
    if spec.loinc == "48765-2":  # Allergies
        return [r for r in resources if r["resourceType"] == "AllergyIntolerance"]
    if spec.loinc == "10160-0":  # Medication Summary
        return [
            r
            for r in resources
            if r["resourceType"] in ("MedicationAdministration", "MedicationStatement")
        ]
    if spec.loinc == "8716-3":  # Vital Signs (proposed)
        return [r for r in resources if r["resourceType"] == "Observation" and _is_vital(r)]
    if spec.loinc == "47519-4":  # Procedures (proposed)
        return [r for r in resources if r["resourceType"] == "Procedure"]
    if spec.loinc == "48768-6":  # Payers (IG-defined, optional)
        return [r for r in resources if r["resourceType"] == "Coverage"]
    if spec.loinc == "28568-4":  # EMS Narrative (proposed)
        return [r for r in resources if r["resourceType"] == "DocumentReference"]
    if spec.loinc == "46240-8":  # EMS Course (proposed): operational facts,
        # exam findings, timeline, prearrival Communication — everything the
        # document must carry that no clinical section claims.
        return [
            r
            for r in resources
            if (
                r["resourceType"] == "Observation"
                and _has_category(r, "survey", "exam", "social-history")
            )
            or r["resourceType"] == "Communication"
        ]
    return []


SECTIONS = [
    SectionSpec("Problems", "11450-4", proposed=False, mandatory=True, nv_source="eSituation.11"),
    SectionSpec("Allergies and Intolerances", "48765-2", proposed=False, mandatory=True, nv_source="eHistory.06"),
    SectionSpec("Medication Summary", "10160-0", proposed=False, mandatory=True, nv_source="eMedications.03"),
    SectionSpec("Payers", "48768-6", proposed=False, mandatory=False, nv_source="ePayment.01"),
    SectionSpec("Vital Signs", "8716-3", proposed=True, mandatory=False, nv_source="eVitals.01"),
    SectionSpec("Procedures", "47519-4", proposed=True, mandatory=False, nv_source="eProcedures.03"),
    SectionSpec("EMS Course", "46240-8", proposed=True, mandatory=False, nv_source=None),
    SectionSpec("EMS Narrative", "28568-4", proposed=True, mandatory=False, nv_source="eNarrative.01"),
]


def _empty_reason(ctx: MappingContext, spec: SectionSpec) -> dict:
    nv_code = None
    if spec.nv_source:
        element = ctx.pcr.first(spec.nv_source)
        if element is not None and element.nv:
            nv_code = element.nv
    return nv_pn.section_empty_reason(nv_code)


def _confidentiality(ctx: MappingContext) -> str:
    for resource in ctx.resources:
        for label in resource.get("meta", {}).get("security", []):
            if label.get("code") == "R":
                return "R"
    return "N"


def build_composition(ctx: MappingContext, variant: str = "CR") -> dict:
    """Build the mPSC Composition over the in-memory graph.

    variant: "CR" (Complete Report) or "CS" (Clinical Subset for handoff —
    same sections today; CS trims repeating history at entry level later).
    """
    composition: dict = {
        "resourceType": "Composition",
        "id": ctx.rid("Composition", variant),
        "status": "final",
        "type": MPSC_COMPOSITION_TYPE,
        "subject": ctx.patient_ref(),
        "encounter": ctx.encounter_ref(),
        "title": f"EMS Paramedicine Summary of Care ({variant})",
        "confidentiality": _confidentiality(ctx),
        "identifier": {
            "system": systems.PCR_ID,
            "value": ctx.pcr_number or "unknown",
        },
        "author": [
            {"reference": f"Organization/{ctx.organization_id}"}
            if ctx.organization_id
            else {"display": "EMS agency"}
        ],
    }
    date = (
        ctx.pcr.value("eTimes.12")
        or ctx.pcr.value("eTimes.11")
        or ctx.pcr.value("eTimes.03")
    )
    if date:
        composition["date"] = date

    sections = []
    for spec in SECTIONS:
        resources = _section_resources(ctx, spec)
        if variant == "CS" and spec.loinc == "8716-3" and resources:
            # Clinical Subset carries the last vitals set only (handoff moment).
            last_effective = max(
                (r.get("effectiveDateTime", "") for r in resources), default=""
            )
            resources = [
                r for r in resources if r.get("effectiveDateTime", "") == last_effective
            ]
        if not resources and not spec.mandatory:
            continue
        section: dict = {
            "title": spec.title,
            "code": {"coding": [{"system": systems.LOINC, "code": spec.loinc}]},
        }
        if resources:
            section["entry"] = [
                {"reference": f"{r['resourceType']}/{r['id']}"} for r in resources
            ]
        else:
            section["emptyReason"] = _empty_reason(ctx, spec)
        sections.append(section)
    composition["section"] = sections
    return ctx.add(composition)


def _collect_references(value, refs: set[str]) -> None:
    if isinstance(value, dict):
        ref = value.get("reference")
        if isinstance(ref, str) and "/" in ref:
            refs.add(ref)
        for v in value.values():
            _collect_references(v, refs)
    elif isinstance(value, list):
        for v in value:
            _collect_references(v, refs)


def _rewrite_references(value, mapping: dict[str, str]) -> None:
    """Rewrite `Type/id` references to their urn:uuid form, in place."""
    if isinstance(value, dict):
        ref = value.get("reference")
        if isinstance(ref, str) and ref in mapping:
            value["reference"] = mapping[ref]
        for v in value.values():
            _rewrite_references(v, mapping)
    elif isinstance(value, list):
        for v in value:
            _rewrite_references(v, mapping)


def document_bundle(ctx: MappingContext, composition: dict) -> dict:
    """FHIR document Bundle (Composition first) for ITI-65 / PCC-1 packaging.

    The document is a PROJECTION, not the whole graph: per the FHIR document
    rules every entry must be reachable from the Composition, so we take the
    reference closure from it (forward), plus Provenance (backward-reachable —
    it targets the included resources). Operational resources no section claims
    (e.g. PractitionerRole) stay in the transaction but out of the document.

    Document entries are DEEP COPIES with all internal references rewritten to
    urn:uuid form (relative `Type/id` references cannot resolve against
    urn:uuid fullUrls) and Provenance targets trimmed to document members; the
    transaction bundle keeps the original literal-reference resources.
    """
    import copy

    by_ref = {f"{r['resourceType']}/{r['id']}": r for r in ctx.resources}
    reachable: set[str] = set()
    frontier: set[str] = set()
    _collect_references(composition, frontier)
    while frontier:
        ref = frontier.pop()
        if ref in reachable or ref not in by_ref:
            continue
        reachable.add(ref)
        next_refs: set[str] = set()
        _collect_references(by_ref[ref], next_refs)
        frontier |= next_refs - reachable

    resources = [copy.deepcopy(composition)]
    for r in ctx.resources:
        if r is composition:
            continue
        key = f"{r['resourceType']}/{r['id']}"
        if key in reachable:
            resources.append(copy.deepcopy(r))
        elif r["resourceType"] == "Provenance":
            provenance = copy.deepcopy(r)
            provenance["target"] = [
                t for t in provenance.get("target", []) if t.get("reference") in reachable
            ]
            resources.append(provenance)  # backward-reachable via its targets

    urn_map = {
        f"{r['resourceType']}/{r['id']}": f"urn:uuid:{r['id']}" for r in resources
    }
    for r in resources:
        _rewrite_references(r, urn_map)

    bundle: dict = {
        "resourceType": "Bundle",
        "type": "document",
        "identifier": {"system": systems.PCR_ID, "value": ctx.pcr_number or "unknown"},
        "entry": [
            {"fullUrl": f"urn:uuid:{r['id']}", "resource": r} for r in resources
        ],
    }
    if composition.get("date"):
        bundle["timestamp"] = composition["date"]
    return bundle
