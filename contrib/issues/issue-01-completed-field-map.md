# Contribution offer: completed NEMSIS 3.5.0 → FHIR field map for NEMSIS-Mapping.html

**Summary.** The NEMSIS→FHIR mapping table (`NEMSIS-Mapping.html`, v2.0.0-draft
CI build) has its FHIR-path column empty on roughly 90% of rows. We have
authored and implemented a complete superset mapping — every national NEMSIS
3.5.0 element dispositioned — and would like to contribute it to fill the
table.

**What the contribution contains** (212 rows across 14 panels; markdown per
panel + one CSV):

- Target FHIR resource, US Core profile where applicable, and FHIR path for
  every element (Mapped), or an explicit disposition (Seeded/Deferred) where
  a target is intentionally postponed — nothing silently dropped.
- **NV/PN semantics** per element: NEMSIS Not-Values (7701xxx on `xsi:nil`
  elements) → `data-absent-reason` (+ section `emptyReason`); Pertinent
  Negatives (8801xxx) → negation semantics (`statusReason`, negated
  resources, NKDA). Converters that skip `xsi:nil` destroy pertinent
  negatives — the mapping makes the handling explicit per element.
- **Repeating-group rules**: VitalGroup/MedicationGroup/ProcedureGroup → one
  resource per instance sharing the group's `.01` timestamp.
- Terminology bindings per element (SNOMED/RxNorm/ICD-10-CM pass-through
  vs NEMSIS-coded with ConceptMap), aligned to the IG's NEMSIS CodeSystem
  canonical URL.

**Evidence it works.** The map is executed by an open-source translation
engine (emsInterop, Apache-2.0): a six-case golden corpus (cardiac arrest,
MCI, interfacility, pediatric, refusal, chest pain) passes US Core 6.1.0
declared-profile validation and the official HL7 validator with 0 errors,
document bundles included. StructureMaps (FML) + logical models exist for
the core panels and are CI-checked against the reference Java engine.

**Proposed form.** Whatever suits the editors: a PR replacing the mapping
page's table source, the CSV as an IG input, or the markdown tables as a
starting point for review. We're happy to rework the format.

Artifacts: <https://github.com/FHIRmedicConsulting/emsInterop> —
`contrib/fieldmap/` (tables), `maps/` (FML + ConceptMaps + logical models),
`docs/02_NEMSIS35_to_FHIR_S2T_Mapping.xlsx` (source workbook).
