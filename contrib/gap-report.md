# mPSC IG gap report — verified 2026-08-07

Target: **mPSC v2.0.0-draft** CI build (footer date 2025-10-30),
<https://build.fhir.org/ig/IHE/PCC.PCS/>. Each item: the finding as verified
on that date, its impact, and what this project offers upstream. Items 1–7
are observations of the current build; 8–10 are design-level proposals.

Quick re-probes before submitting anywhere (if the CI build has moved):
`NEMSIS-Mapping.html` FHIR-path column density · `CodeSystem-NEMSIS.html`
search "TODO: JFM" · `StructureDefinition-IHE.PCC.FHIR.MS.Composition.html`
section slice count.

| # | Finding (verified) | Impact | Offered upstream |
|---|---|---|---|
| 1 | `NEMSIS-Mapping.html`: FHIR-path column empty on ~90–95% of rows (only scattered entries like `Organization.identifier`, `Observation.value[x]`) | Every integrator re-invents the field mapping | The completed 212-row superset map (`fieldmap/`), panel-by-panel, with NV/PN semantics, terminology bindings, and repeating-group rules — proposal-01 |
| 2 | Medical Summary Composition profile defines 3 mandatory sections (Problems 11450-4, Allergies 48765-2, Medications) with open slicing; no vitals/procedures/EMS-course/narrative sections | Most clinical panels have no document home | Proposed sections — Vital Signs 8716-3, Procedures 47519-4, EMS Narrative 28568-4, EMS Course 46240-8 — implemented and validator-clean in this project — proposal-04 |
| 3 | eOutcome delegated to QRPH "QORE" with no binding/profile linked (workbook finding; unchanged) | Outcome loop unrepresentable in the IG | Interim model (Observation/Encounter cluster) + working outcome loop (ADT + FHIR discharge rails) as implementation evidence — proposal-05 |
| 4 | `CodeSystem-NEMSIS.html`: 18 placeholder concepts with `TODO: JFM …` displays, incl. malformed codes `99270235`, `C7`, `todo1` | Terminology cannot be depended on at runtime | Clean registry-derived CodeSystem (2,321 concepts, `content=fragment`), 205 per-element ValueSets, 7 ConceptMaps — the `emsinterop.nemsis` package — proposal-02 |
| 5 | Element-id typos present: `deDisposition.15` (for eDisposition.15), `deOther.21` (for eOther.21), `EPSAP` (for E-PSAP, eTimes.01 label) | Breaks automated consumption of the table | Corrected ids throughout the field map; errata list — proposal-03 |
| 6 | Missing elements confirmed: table skips eResponse.15, eArrest.05, eArrest.06, eArrest.08; ePayment ordering anomalies | Table is not a reliable element inventory | Reconciliation against the NEMSIS v3.5.0 data dictionary (the field map is complete per panel) — proposal-03 |
| 7 | No NEMSIS version declared anywhere on the mapping page | Ambiguous source scope (3.4? 3.5.0? 3.5.1?) | Request an explicit version pin; our map is scoped NEMSIS 3.5.0 with 3.5.1 deltas flagged — proposal-03 |
| 8 | US Core alignment not asserted (race/ethnicity via `pcc-uv-*` extensions only) | US-realm implementers diverge from US Core expectations | Dual-carry pattern (US Core + pcc-uv), demonstrated in the mapper — proposal-06 |
| 9 | Published vs master branch drift (e.g. MedicationAdministration profile exists on master only) | Moving target for implementers | Request a stable release cadence / ballot snapshot — proposal-06 |
| 10 | EMS-Overall names no ITI transaction numbers; transport binding loose | Interop endpoints under-specified | ITI-65 (MHD Provide Document Bundle) as the default binding, working in this project — proposal-06 (an EMS-Overall concern, routed by the editors) |
