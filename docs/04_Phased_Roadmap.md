# Phased Build Roadmap — emsInterop
NEMSIS 3.5 → IHE EMS (mPSC / US Core) FHIR translation engine
Date: 2026-08-06 · Status: **all phases delivered as of v0.3.0 (2026-08-08)**

> **Delivery status.** P0–P5 shipped across v0.1.0–v0.3.0; P6 (outcome loop,
> reverse mapping, at-the-door push) and P7 (upstream contribution package)
> shipped in v0.3.0 — both ahead of their "future / post-MVP" planning position
> below, which is left unedited as the historical plan of record. What remains is
> not phase work but **field hardening**: production PHI enablement, a
> larger corpus from real agency exports, and whatever the mPSC IG returns.
> See `CHANGELOG.md` for what each release contains and the README's
> "Scope & limitations" for what alpha still means.

Effort bands are relative (S ≈ days, M ≈ 1–2 wks, L ≈ 3–6 wks, XL ≈ quarter); treat as planning shape, not commitments. Risk = likelihood × impact on delivery. **Runtime (rev 2): native Python mapper → fhirEngine REST; Delta OSS is fhirEngine's backing store; no Databricks/Spark (ADR-002/009/010).**

---

## Phase 0 — Foundations & decisions (S–M)
**Goal:** lock the ground truth so later phases don't churn.
- Confirm **source NEMSIS versions** actually emitted by your feeds (3.5.0 CP level vs 3.5.1) — drives XSD pinning + ADR-007. *(Open question — external dependency.)*
- **Pin IG package versions**: `ihe.pcc.mpsc`, `ihe.pcc.ems-overall`, `hl7.fhir.uv.ips`, `hl7.fhir.us.core@6.1.0`. Snapshot; never build against floating `-current`.
- **Stand up fhirEngine** at a pinned release, `single` mode for dev; **install the IG packages** (US Core 6.1.0, IPS, mPSC) into fhirEngine and set `FHIRENGINE_VALIDATION_PROFILES` so Tier-1 validation enforces them. Confirm the fail-closed prod overlay path for later.
- Stand up the **canonical FHIR data model** decision (US Core alignment map) and the deviation allow-list skeleton (ADR-006).
- Ratify ADRs 001–010.
**Exit:** versions pinned, fhirEngine running with IG packages installed, ADRs accepted, source-version answer in hand.
**Effort S–M · Risk: Med** (external version confirmation can slip; fhirEngine is pre-alpha).

## Phase 1 — Ingest, parse, validate (source side) (M)
**Goal:** trustworthy typed intermediate model.
- Land `EMSDataSet` XML + source metadata (agency, version, hash) in a **raw-NEMSIS bronze Delta table via delta-rs (`deltalake` Python)**; shred to one row per `PatientCareReport`. (Separate from fhirEngine's internal FHIR tiers.)
- **XSD validation** (pinned schema) → quarantine on structural failure with machine-readable `OperationOutcome`.
- **Schematron/business rules** as warnings.
- Build the **normalized intermediate model** preserving **NV/PN attributes and `xsi:nil`** as first-class fields (the make-or-break detail).
**Exit:** sample corpus parses to intermediate model with NV/PN intact; quarantine path proven.
**Effort M · Risk: Low–Med.**

## Phase 2 — Golden test corpus & harness (M) — *do this before heavy mapping*
**Goal:** regression spine so mapping work is verifiable.
- Curate representative NEMSIS 3.5 PCRs: **NV/PN edge cases, cardiac arrest, MCI/triage, interfacility transfer, pediatric length-based, refusal/no-transport, multi-vitals-set, prior-to-EMS-care provenance.**
- Author expected FHIR outputs for each (hand-built, reviewed).
- Wire a **two-tier validation harness**: Tier-1 = submit to fhirEngine (`$validate` / transaction against installed profiles); Tier-2 = external HL7 validator for authoritative mPSC/IPS L5. Add an **optional Matchbox/HAPI FML oracle** that runs the StructureMaps and diffs against the native Python output.
**Exit:** red/green harness runs in CI against the corpus (both tiers + oracle).
**Effort M · Risk: Med** (expected-output authoring is exacting).

## Phase 3 — Canonical mapper, Layer A (L–XL) — *the bulk of the work*
**Goal:** NEMSIS → US-Core-aligned resource graph.
Sequenced by clinical value + reuse:
1. **Encounter spine** (`eTimes`/`eResponse`/`eDispatch`/`eDisposition`) + `Organization` (`dAgency`, IG-anchored) + `Practitioner/Role` (crew).
2. **Patient** (`ePatient`, incl. `.25` sex logic, race/ethnicity reconciliation).
3. **Vitals** (`eVitals` → US Core Vital Signs; group→N Observations sharing timestamp; GCS/AVPU/pain/stroke scales).
4. **Medications** (`eMedications` → MedicationAdministration, RxNorm) + **Procedures** (`eProcedures`/`eAirway` → Procedure, SNOMED).
5. **Situation/History** → Condition/AllergyIntolerance/MedicationStatement (feeds mPSC sections).
6. **Arrest, Injury, Exam, Labs, Device** → Observation/Procedure/Media clusters.
7. **Coverage** (`ePayment`), **DocumentReference/Media** (`eNarrative`,`eOther`), **eCustom** (Observation).
Cross-cutting, built alongside #1: **NV/PN engine**, **ConceptMaps (applied in-mapper)**, **deterministic UUIDv5 ids + conditional references**, **DS4P tagging**, **Provenance**.
Implementation: **StructureMaps + ConceptMaps authored as spec, executed natively in Python** (ADR-002); thin typed helper layer for awkward transforms; **submit transaction Bundles to fhirEngine** and **register resulting ValueSets/CodeSystems** into fhirEngine so bound codes pass `$validate-code`.
**Exit:** every national NEMSIS element dispositioned (Mapped/Seeded/Deferred/Upstream); corpus green through fhirEngine Tier-1 + external US Core.
**Effort L–XL · Risk: High** (breadth, terminology, native-exec correctness). *Mitigation:* panel-by-panel, corpus-gated, CI FML oracle; the S2T workbook is the running spec.

## Phase 4 — Document assembly, Layer B (M–L)
**Goal:** mPSC-CS and mPSC-CR bundles.
- Build `IHE.PCC.FHIR.MS.Composition` with pluggable **section builders** (IG sections now; proposed Vitals/Procedures/EMS-Course/Narrative/Results toggled).
- Assemble **from the mapper's in-memory canonical graph** and submit the document in the **same transaction** as its resources (avoids `medallion` read-after-write race, §5.5a); `emptyReason`/`ihe-pcc-comp-1` handling driven by the NV engine.
- **mPSC-CS** (handoff subset) vs **mPSC-CR** (complete) profiles of the assembler.
- Validate Layer B vs mPSC + IPS (fhirEngine Tier-1 + external validator Tier-2).
**Exit:** both document variants validate; content-completeness review vs a real PCR.
**Effort M–L · Risk: Med–High** (mPSC draft instability). *Mitigation:* thin layer, pinned versions.

## Phase 5 — Packaging, transport & operationalization (M)
**Goal:** deliverable, governed pipeline.
- **ITI-65 Provide Document Bundle** packager behind the transport interface (XDR/XDM/file adapters), sourced from fhirEngine `$export`/`read` (ADR-008).
- **fhirEngine fail-closed prod profile** enabled (auth/audit/TLS gates) before any PHI; DS4P tagging verified end-to-end; PHI-safe mapper logging; **DuckDB de-identified projection** over Gold (§7).
- `medallion` promotion via **`fhirengine-promote`/Dagster OSS** (no Spark); **conversion issue log ↔ fhirEngine dead-letter** reconciliation feeding the gap register.
- CI/CD for the mapping ruleset (versioned StructureMaps/ConceptMaps release; IG-package + terminology load into fhirEngine).
**Exit:** end-to-end raw-NEMSIS-bronze → fhirEngine (Delta) → ITI-65 for the corpus, governed and observable.
**Effort M · Risk: Med.**

## Phase 6 — Outcome loop & FHIR→NEMSIS (L) — *future*
**Goal:** close the EMS-Overall loop.
- Retrieve hospital **Discharge Summary** (LOINC 18842-5), extract outcomes → NEMSIS `eOutcome` → State Registry.
- Reverse mapping (FHIR → NEMSIS) reusing ConceptMaps in reverse.
- Real-time **at-the-door push** endpoint reusing the same Python mapper + fhirEngine (`single` mode for read-after-write).
**Exit:** demonstrated outcome write-back on a pilot pairing.
**Effort L · Risk: High** (cross-org exchange, identity matching). *Deferred.*

## Phase 7 — Upstream contribution (ongoing, parallel from Phase 3)
**Goal:** turn the superset into standards influence.
- Package cleaned `NEMSIS` CodeSystem, ConceptMaps, proposed Composition sections, and the completed field map as an **IHE PCC / HL7 EMS WG** contribution.
- Feed gaps/defects (typos `deDisposition.15`/`deOther.21`, TODO concepts, missing `eResponse.15`, no clinical sections) back to the IG maintainers.
**Exit:** submission(s) filed; tracked against IG issues.
**Effort: ongoing · Risk: Low** (reputational upside; aligns with FHIRmedic positioning).

---

### Critical path & parallelism
- Critical path: **P0 → P1 → P3 → P4 → P5.**
- Run **P2 (corpus)** just ahead of P3 and keep it green throughout.
- Run **P7 (upstream)** in parallel from mid-P3 — the mapping artifacts are the contribution.
- **P6** is post-MVP.

### Biggest risks, consolidated
1. **P3 breadth + native-exec correctness** (High) → panel-by-panel, corpus-gated, CI FML oracle, typed helper layer.
2. **mPSC draft instability** (Med–High) → thin Layer B, pinned versions, track repo.
3. **fhirEngine pre-alpha maturity** (Med) → pin a release, fail-closed prod profile before PHI, Tier-2 external validator authoritative.
4. **Source-version heterogeneity** (Med) → detect + normalize (ADR-007), confirm feeds in P0.
5. **Terminology completeness + no `$translate` in fhirEngine** (Med) → ConceptMaps applied in-mapper + dual-coding; register ValueSets for `$validate-code`.
6. **NV/PN correctness** (Med, high blast radius) → first-class in the intermediate model + dedicated corpus cases.
