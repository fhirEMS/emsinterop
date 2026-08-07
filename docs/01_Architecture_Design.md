# NEMSIS 3.5 → IHE EMS FHIR Translation Engine
## System Architecture & Design

**Project:** nemsis2FHIR
**Author:** FHIRmedic (Chad) — design dive prepared with Claude
**Date:** 2026-08-06
**Status:** Draft for review
**Scope of this document:** End-to-end architecture for converting NEMSIS v3.5 EMS Patient Care Report (ePCR) XML into IHE-conformant FHIR R4, using a *layered* target model (canonical resource graph → mPSC IPS document), an *upstream-ready superset* mapping, and a runtime grounded in **Chad's own fhirEngine OSS server on OSS Delta Lake** (no Databricks).

**Runtime substrate (revision 2):** the FHIR system of record and repository is **fhirEngine** — Chad's Apache-2.0 FHIR R4 server: a **TypeScript/Hono REST tier over a delta-rs / DataFusion storage engine via a Python sidecar**, with a `Warehouse` seam, `single|medallion` storage modes, validation-prior-to-Bronze, IG-package install, a built-in terminology server, deterministic MPI at promotion, and SMART/UDAP/consent/DS4P enforcement. **Delta OSS is fhirEngine's backing store.** Databricks is out of scope. This revision rewrites §5, §7, §8, §9 and ADR-002 accordingly.

---

## 0. TL;DR for the impatient architect

1. **"The IHE EMS spec" is a family of two IGs, not one.** The URL you started from — **IHE EMS-Overall** (`ihe.pcc.ems-overall`, v0.1.1, R4) — is an *umbrella workflow guide*. It defines actors (Ambulance, HIE, Hospital, State Registry) and leans on the IHE document-sharing toolbox (MHD/ITI-65, PDQm, PIXm, XDS/XCA/XCPD, XDR, MHDS). It contains **essentially no computable content** — its Artifacts page defines a single dummy `Patient`. The actual content model lives in a sibling IG: **IHE PCC mobile Paramedicine Summary of Care (mPSC)** (`ihe.pcc.mpsc`, v2.0.0-draft, R4), the FHIR-era successor to the 2018 CDA "Paramedicine Care Summary (PCS)" supplement.

2. **The official NEMSIS→FHIR map is ~90% empty.** The mPSC `NEMSIS-Mapping` page is really a NEMSIS element *inventory* (~330 rows). The FHIR-target column is populated for only ~11 rows (`dAgency.*` → `Organization`, `eCustomConfiguration.*` → `Observation`). `eOutcome.*` is explicitly punted to an external QRPH "QORE" profile. **You are authoring the clinical mapping**, not consuming one.

3. **The mPSC document skeleton is thin.** The `FHIR Medical Summary` Composition (IPS-derived) currently defines only four sections — Problems (LOINC 11450-4), Allergies (48765-2), Medication Summary (10160-0), and optional Payers (48768-6). There is **no vitals / procedures / EMS-narrative section yet**, so most clinical panels have no home section in the current draft. The profile set (`MedicationAdministration`, `Patient.Activity`, …) is being built branch-by-branch and is unstable.

4. **Therefore the design must be layered by necessity, not just preference.** Map NEMSIS → a **canonical, profile-validated FHIR R4 resource graph** first (the durable asset), then *assemble* the mPSC document as a thin, swappable projection over that graph. When mPSC stabilizes, only the assembly layer changes; the resource-level mapping — the 90% of the work — is preserved.

5. **Recommended runtime (revised for fhirEngine + Delta OSS).** Build the converter as a **Python "nemsis2fhir mapper" service** that parses NEMSIS XML, applies ConceptMaps, assembles the canonical resource graph **and** the mPSC document Bundle in one pass, and **submits a FHIR transaction Bundle to fhirEngine's REST API**. fhirEngine then does what it already does well — **validation-prior-to-Bronze, search indexing, Delta persistence (delta-rs/DataFusion sidecar), history/versioning, deterministic MPI at promotion, terminology `$validate-code`, security/consent/DS4P enforcement, and serving** (`read`/`$everything`/`$export`). **StructureMaps + ConceptMaps stay the authored, upstream-contributable spec**, but are **executed natively in Python** (no JVM/Matchbox in the hot path); an optional Matchbox/HAPI FML run in CI acts as a fidelity *oracle*. Delta OSS is the single storage substrate (fhirEngine-owned); DuckDB reads the same Gold tables for analytics. No Spark, no Databricks. Full comparison in §9 and ADR-002/009/010.

---

## 1. Goals, non-goals, and success criteria

### 1.1 Goals
- Convert a NEMSIS v3.5 `EMSDataSet` ePCR (one or many `PatientCareReport` records) into:
  - a **canonical FHIR R4 resource graph** (Patient, Encounter, Organization, Practitioner/PractitionerRole, Observation, MedicationAdministration, Procedure, Condition, AllergyIntolerance, Location, DocumentReference, Provenance), profile-validated and US-Core-aligned where a US Core profile exists; then
  - an **mPSC IPS-style FHIR Document Bundle** — both the **Clinical Subset (mPSC-CS)** for handoff and the **Complete Report (mPSC-CR)** for longitudinal/quality use — carried by a `Composition` conforming to `IHE.PCC.FHIR.MS.Composition`.
- Package the document for exchange per the mPSC Content Creator **FHIR Option** (Provide Document Bundle **ITI-65** / **PCC-1**).
- Provide a **complete, upstream-ready superset mapping** (fills the IG's empty cells) that can be proposed to IHE PCC / the HL7 EMS Work Group.
- Preserve full **traceability and data provenance** from each FHIR element back to its NEMSIS element ID and source `CorrelationID`.

### 1.2 Non-goals (this phase)
- The reverse path (FHIR → NEMSIS) and the **outcome write-back loop** (hospital discharge summary → NEMSIS `eOutcome` → state registry). Designed-for but not built (see roadmap Phase 6).
- Implementing the HIE query/retrieve actors themselves (PDQm/XCA endpoints). We produce and package content; we are a **Content Creator**, not the exchange fabric.
- CDA output. mPSC also defines a CDA Option; out of scope here (kept behind an interface — see §5.7).
- Real-time sub-second conversion. Target is near-real-time-per-record and batch; see NFRs.

### 1.3 Success criteria
- 100% of NEMSIS 3.5 *national* elements (the `e`/`d` dataset, excluding state/custom) are accounted for in the mapping workbook with a disposition of **Mapped / Seeded / Deferred / Upstream-proposed** — no silent drops.
- Generated bundles pass the FHIR R4 validator against the mPSC profiles and (where applicable) US Core 6.1.0, with a documented, reviewed list of accepted deviations.
- Every generated resource carries a `Provenance` (or `meta.source` + mapping-version tag) that resolves to the mapping ruleset version and the source PCR.
- The mapping ruleset is expressible as StructureMaps/ConceptMaps that a standard FML engine (Matchbox) can run unchanged as a CI fidelity oracle (portability proof), even though production execution is native Python.

---

## 2. The two-IG landscape (authoritative framing)

| | **EMS-Overall** | **mPSC (PCC.PCS)** |
|---|---|---|
| Package id | `ihe.pcc.ems-overall` | `ihe.pcc.mpsc` |
| Role | Umbrella workflow / white paper | Content definition (document + profiles + NEMSIS map) |
| FHIR | R4 (4.0.1) | R4 (4.0.1) |
| Version / status | 0.1.1-current, *not an authorized publication* | 2.0.0-draft, CI build, many TODOs |
| Computable artifacts | 1 (dummy Patient) | 2 published profiles (Composition, Patient) + 2 extensions + 2 code systems; more in `master` branch |
| What it gives you | Actor/transaction narrative; document-sharing bindings; outcome-loop concept | The `Composition` skeleton, `NEMSIS` code system stub, `dAgency` anchor mappings, actor/option model |

**Design consequence:** treat **EMS-Overall as the *interaction* contract** (who sends what to whom, and with which IHE transaction) and **mPSC as the *content* contract** (what the payload looks like). Our engine sits at the Content Creator role in mPSC and produces payloads that EMS-Overall's Paramedicine Care Flow and Routine Interfacility Patient Transport use cases move around.

### 2.1 Actors & transactions we must satisfy (from EMS-Overall + mPSC)
- **Ambulance = Content Creator / Document Source.** Our engine's role.
- **Push at handoff:** Provide Document Bundle **[ITI-65]** (FHIR/MHD) to the receiving Hospital / Document Recipient; mPSC's own **[PCC-1]** Document Sharing transaction. Optional groupings: XDS.b Document Source, XDM Portable Media Creator, XDR Document Source (all *encouraged, not required* — the transport binding is deliberately loose).
- **Consume before handoff (context):** patient discovery (PDQm/PIXm/XCPD) + query/retrieve of any existing Medical Summary (LOINC **34133-9**) — informs but does not block our creation path.
- **Outcome loop (future):** retrieve hospital Discharge Summary (LOINC **18842-5**), extract, write back to NEMSIS `eOutcome` → State Registry.

> ⚠️ **Spec-maturity flags to carry into every design review:** EMS-Overall states no ITI transaction numbers (the ITI-65/78 bindings are inferred from profile families); mPSC's profile set differs between published and `master` builds; the `NEMSIS` code system has ~13 `TODO: JFM` placeholder concepts and at least one malformed entry. **Pin the exact IG package versions in your build** and snapshot them — do not build against `-current`/CI floating heads.

---

## 3. Source model: what NEMSIS 3.5 actually hands you

A NEMSIS v3.5 ePCR is a single `EMSDataSet` XML document containing one or more `PatientCareReport` records. Structure that drives the mapping:

- **Sections & groups.** Elements are `eXxx.NN` within sections; clinical panels are **repeating groups** (`eVitals.VitalGroup`, `eMedications.MedicationGroup`, `eProcedures.ProcedureGroup`, `eArrest`, `eExam`, `eOutcome…`). Each group instance is timestamped by its own `.01` (e.g., `eVitals.01` timestamps every measurement in that VitalGroup). **This one-timestamp-per-group fact is the backbone of Observation grouping** (see §4.3).
- **Record key & identity.** `eRecord.01` (PCR Number) is the record key; NEMSIS separately uses **UUIDs** (per the NEMSIS V3 UUID Guide) for stable global identity; `CorrelationID` is a *within-document* linking token (primarily to bind custom `eCustomResults` to a specific national element/group instance) — **not** a global key.
- **The Not-Value (NV) / Pertinent-Negative (PN) mechanic — the single most important source subtlety.**
  - `NV` (7701xxx family: `7701001` Not Applicable, `7701003` Not Recorded, `7701005` Not Reporting, "Not Known", …) carried with `xsi:nil="true"` means *there is no real value and here's why*. → maps to **`data-absent-reason`**, not to a fabricated value.
  - `PN` (8801xxx family: contraindication noted, refused, denied by order, no known drug allergy, …) means *a clinically meaningful negative*. → maps to **negation semantics** (`MedicationAdministration.statusReason`, negated `AllergyIntolerance`, `Observation` with negative interpretation), never dropped.
  - Both attributes can decorate the same nil element. A converter that treats nil as "skip" silently destroys clinically meaningful negatives — an explicit anti-pattern to guard against in tests.
- **Terminology already in the source.** *(Corrected 2026-08-06 against the pinned 3.5.0 XSDs, which pattern-check these fields.)* `eProcedures.03` is **SNOMED CT**; `eMedications.03` is **RxNorm**; `eSituation.09–.12` (symptoms + provider impressions) and `eHistory.08` (PMH) are **ICD-10-CM** — *not* SNOMED as earlier drafts of this document stated. `eProcedures.07` complications are NEMSIS-coded (3907xxx). These are *pass-through with system tagging*, not re-coding.
- **Numeric NEMSIS code sets.** Most non-free-text, non-external-terminology elements use NEMSIS integer code sets (e.g., `2223001` Emergent, `4232005` ALS-Paramedic, `9927023` IV route). These need **ConceptMaps** to standard systems (SNOMED/LOINC/v3-Race/etc.) or, where no target exists, representation via the mPSC `NEMSIS` `CodeSystem`.
- **Date/time.** ISO 8601 **with required offset** (min `1950-01-01`), plus date-only/time-only simple types → straight to FHIR `dateTime`/`instant`, offset preserved.
- **3.5.0 vs 3.5.1 and a deprecation trap.** `ePatient.13 Gender` is **deprecated in 3.5.0**, replaced by `ePatient.25 Sex`. The mPSC inventory still lists `.13`. Your mapping must prefer `.25` and treat `.13` as legacy fallback (ADR-007). Confirm whether your source systems emit 3.5.0-CPx or 3.5.1.

---

## 4. Target model: the layered FHIR representation

```
NEMSIS 3.5 EMSDataSet (XML)
        │  parse + XSD/Schematron validate
        ▼
 ┌─────────────────────────────────────────────┐
 │  LAYER A — Canonical FHIR R4 resource graph  │   ← durable asset; 90% of the mapping work
 │  Patient, Encounter (spine), Organization,   │
 │  Practitioner/Role, Location, Observation,   │
 │  MedicationAdministration, Procedure,        │
 │  Condition, AllergyIntolerance,              │
 │  DocumentReference, Provenance               │
 │  validated vs US Core 6.1.0 where applicable │
 └─────────────────────────────────────────────┘
        │  document assembly (thin projection)
        ▼
 ┌─────────────────────────────────────────────┐
 │  LAYER B — mPSC IPS Document Bundle          │   ← swappable as mPSC stabilizes
 │  Composition (IHE.PCC.FHIR.MS.Composition)   │
 │  → mPSC-CS (Clinical Subset)                 │
 │  → mPSC-CR (Complete Report)                 │
 └─────────────────────────────────────────────┘
        │  package
        ▼
   Provide Document Bundle [ITI-65] / [PCC-1]
```

### 4.1 The Encounter is the spine
NEMSIS has no first-class "encounter" element, but every clinical panel is implicitly *about one prehospital encounter*. We synthesize a single **`Encounter`** per `PatientCareReport` and hang timing, disposition, and provenance from it:
- `eTimes.*` → `Encounter.period` (`.06` arrived on scene / `.09` left scene / `.11` arrived at destination / `.12` transfer of care) plus discrete `Observation`s or an `Encounter`-linked timeline for the finer timestamps.
- `eResponse` + `eDispatch` → `Encounter.serviceType`, `Encounter.hospitalization`, `EncounterHistory`/`Encounter.classHistory`, plus `Encounter.identifier` from `eResponse.03` Incident / `eResponse.04` Response Number.
- `eDisposition.27–.30` (Unit/Patient-care/Crew/Transport disposition — the restructured 3.5 outcome fields) → `Encounter.hospitalization.dischargeDisposition` + `Encounter.status`.
- Every downstream resource references the Encounter (`Observation.encounter`, `MedicationAdministration.context`, `Procedure.encounter`).

### 4.2 Resource assignment (canonical layer), by panel

| NEMSIS panel | Primary FHIR target(s) | US Core profile (if any) | Notes |
|---|---|---|---|
| `eRecord` | `Composition.identifier`, `Bundle.identifier`, `Provenance` | — | PCR number = document/business id |
| `dAgency` | `Organization` (+ `Location`) | US Core Organization | The only IG-anchored mapping; `.01/.02`→identifier, `.03`→name, `.04`→address; `.25`→NPI identifier |
| `dPersonnel` / `eCrew` | `Practitioner` + `PractitionerRole` | US Core Practitioner/Role | Crew IDs in eMedications.09/eProcedures.09 resolve here |
| `ePatient` | `Patient` (`IHE.PCC.Patient`) | US Core Patient | Race/ethnicity via `pcc-uv-race/ethnicity` (mPSC) *and/or* US Core extensions — reconcile (ADR-006); `.25 Sex`→ US Core birthsex / sex extensions |
| `eResponse`,`eDispatch`,`eTimes`,`eScene` | `Encounter` (+ `Location` for scene) | US Core Encounter | Encounter spine; scene GPS→`Location.position` |
| `eSituation` | `Condition` (impression `.11/.12`, ICD-10-CM per 3.5.0 XSD) + `Observation` (complaint, acuity, symptom onset) | US Core Condition (Encounter Dx) | `.11` Provider Primary Impression = principal `Condition`; complaint `.04` may be a `Condition` w/ category or `Observation` |
| `eInjury` | `Observation` (trauma criteria, mechanism) + `Condition` | — | ACN telematics `.11–.29` → `Observation` cluster or `DocumentReference` |
| `eArrest` | `Observation` + `Procedure` (CPR, defib, ROSC) | — | `.01` Cardiac Arrest gate; arrest timeline `.14/.19/.15` → Observation.effective/Procedure.performed |
| `eHistory` | `Condition` (`.08` PMH), `AllergyIntolerance` (`.06/.07`), `MedicationStatement` (`.12–.15,.20`), advance directives (`.05`) | US Core Condition/Allergy/Medication | Feeds mPSC Problems/Allergies/Medication sections directly |
| `eVitals` | `Observation` (vital-signs category), one per measurement, grouped by VitalGroup | US Core Vital Signs (+ specific: BP, HR, SpO2, Resp, Temp) | GCS → US Core / LOINC panel; AVPU, pain, stroke scale → Observation |
| `eLabs` | `Observation` (laboratory) + `DiagnosticReport`/`Media` for imaging | US Core Lab Result | Rare in field data |
| `eExam` | `Observation` (exam findings by body region) | — | Coded findings; PN-heavy (pertinent negatives) |
| `eProtocols` | `Observation`/`CarePlan` reference | — | Protocol used |
| `eMedications` | `MedicationAdministration` (RxNorm) | US Core MedicationAdministration (mPSC `IHE.PCC.mPSC.MedicationAdministration` in master) | Group→one MedAdmin; `.07/.08` response/complication → note/statusReason |
| `eProcedures` | `Procedure` (SNOMED) | US Core Procedure | Group→one Procedure; attempts/success `.05/.06` → outcome/note |
| `eAirway` | `Procedure` + `Observation` (confirmation) | — | Links to eProcedures airway entries |
| `eDevice` | `Observation`/`Device` + `Media` (waveforms) | — | Monitor/defib data; waveform → `Media`/`DocumentReference` |
| `eDisposition` | `Encounter.hospitalization` + `ServiceRequest`/`Location` (destination) | US Core Encounter | Destination facility→`Location`/`Organization`; `.24/.25` prearrival alert |
| `ePayment` | `Coverage` + `Contract`/`InsurancePlan` | US Core Coverage | Feeds mPSC optional Payers section (48768-6) |
| `eOutcome` | *(deferred)* → external QORE / `Observation` cluster | — | IG punts to QORE; future outcome-loop input |
| `eNarrative` | `Composition.section.text` + `DocumentReference` | — | Free-text PCR narrative |
| `eOther` | `DocumentReference`/`Media` (attachments, signatures) | — | Signatures → `Provenance.signature` |
| `eCustomConfiguration`/`eCustomResults` | `Observation` (per IG) | — | Custom elements; `CorrelationID` links result↔config |

### 4.3 Repeating-group → resource-instance rule
For each repeating group, emit **one FHIR resource per group instance**, sharing the group's `.01` timestamp:
- `eVitals.VitalGroup` → *N* `Observation`s (one per measured element present), all with the same `effectiveDateTime = eVitals.01` and the same `Encounter` + optional `hasMember` panel Observation to keep the set together.
- `eMedications.MedicationGroup` → one `MedicationAdministration` (`effectiveDateTime = eMedications.01`).
- `eProcedures.ProcedureGroup` → one `Procedure` (`performedDateTime = eProcedures.01`).
- `eVitals.02 / eMedications.02 / eProcedures.02` "prior to this unit's care" → `Observation`/resource `.performer`/`Provenance` distinction (was it *our* crew or a prior unit). Do not merge the two provenances.

### 4.4 mPSC document assembly (Layer B)
Assemble a `Composition` (`IHE.PCC.FHIR.MS.Composition`, `type` LOINC 107903-7) referencing Layer A resources into IPS-style sections. Current IG sections + our proposed extensions (upstream candidates):

| Section | LOINC | Source resources | Status |
|---|---|---|---|
| Problems | 11450-4 | Condition (eSituation.11/.12, eHistory.08) | IG-defined |
| Allergies & Intolerances | 48765-2 | AllergyIntolerance (eHistory.06/.07) | IG-defined |
| Medication Summary | 10160-0 | MedicationAdministration (eMeds), MedicationStatement (eHistory.12) | IG-defined |
| Payers | 48768-6 | Coverage (ePayment) | IG-defined (optional) |
| **Vital Signs** | **8716-3** | Observation (eVitals) | **Proposed upstream** |
| **Procedures** | **47519-4** | Procedure (eProcedures, eAirway) | **Proposed upstream** |
| **History of Encounters / EMS Course** | **46240-8** | Encounter, eTimes, eDisposition | **Proposed upstream** |
| **EMS Narrative** | **e.g. 28568-4 / custom** | DocumentReference (eNarrative) | **Proposed upstream** |
| **Results (Labs/Imaging)** | **30954-2** | Observation/DiagnosticReport (eLabs) | **Proposed upstream** |

- **mPSC-CS (Clinical Subset):** Problems, Allergies, Medications, Vitals (last set), chief complaint/impression, disposition/destination + prearrival alert. Optimized for the handoff moment.
- **mPSC-CR (Complete Report):** all sections, full repeating history. For longitudinal + quality/registry use.
- **`ihe-pcc-comp-1` constraint:** each mandatory section must have entries *or* an `emptyReason` — so NV/absent handling must reach the section level, not just the resource level.

---

## 5. Component architecture

**Division of labor:** a thin **nemsis2fhir mapper** (new code we build) owns everything NEMSIS-specific up to a validated FHIR transaction Bundle; **fhirEngine** (exists) owns FHIR validation, persistence, indexing, terminology, MPI, security, and serving. The seam between them is the FHIR REST API — nothing more.

```
  ┌──────────────── nemsis2fhir mapper (Python — new) ─────────────────┐      ┌──────────── fhirEngine (exists) ────────────┐
  │ (1)Ingest   (2)Parse+XSD/    (3)Canonical      (4)Ref/Identity      │      │  Hono REST: POST / (transaction)            │
NEMSIS│ raw XML → Schematron  →  Mapper (native  → resolver + det. IDs  │ FHIR │   → auth (SMART/UDAP) + consent/DS4P         │
 XML  │ (Delta      validate      Python exec of   (5b)Doc Assembler    │──txn→│   → validation-prior-to-Bronze              │
      │  bronze)   NV/PN kept      StructureMaps    mPSC-CS / mPSC-CR    │Bundle│      (structural+card+bindings+L4+profile)  │
      │            first-class     + ConceptMaps    (5a)Provenance       │      │   → search-index → DeltaWarehouse           │
      └────────────────────────────────────────────────────────────────┘      │      (delta-rs write / DataFusion read)     │
                    │                                                          │   → MPI dedup at promotion                   │
          (opt) Matchbox/HAPI FML oracle in CI ── fidelity check              │   → serve: read/$everything/$export         │
                                                                               │   → Python sidecar (deltalake+pyarrow)      │
   External HL7 validator ── authoritative mPSC/IPS L5 verdict ───────────────┤   Delta OSS (single | medallion Bronze→Gold)│
                                                                               └─────────────────────────────────────────────┘
                                                                                        │ Gold Delta tables (read-only)
                                                                                        ▼
                                                                                DuckDB — analytics/quality (no Spark)
   Serving → Provide Document Bundle [ITI-65]/[PCC-1] via transport adapter (fhirEngine $export / DocumentReference)
```

### 5.1 (1) Ingest / bronze (mapper)
Land raw `EMSDataSet` XML unchanged in a **Delta OSS bronze table** written via **delta-rs (`deltalake` Python)** — the same substrate fhirEngine uses, so no new storage tech. Capture source metadata: submitting agency, NEMSIS version (`eRecord`/schema namespace), receipt timestamp, file hash. One row per `PatientCareReport` after shredding, keyed by `eRecord.01` + agency + UUID. (This bronze is *raw NEMSIS*, distinct from fhirEngine's internal FHIR Bronze tier.)

### 5.2 (2) Parse & validate — source-side (mapper)
- **XSD validation** against the pinned NEMSIS 3.5.0 (CPx) / 3.5.1 `EMSDataSet` schema (Python `lxml`). Hard-fail structural violations to quarantine.
- **Schematron / national+state business rules** (NEMSIS publishes these) — *warn, don't necessarily fail*: field data is messy; a permissive-with-reporting posture beats dropping records.
- Emit a **normalized intermediate model** (typed, NV/PN attributes preserved as first-class fields). Do **not** collapse nil elements here.

### 5.3 (3) Canonical mapper — the heart (mapper)
- **Spec IR = FHIR StructureMaps (FML) + ConceptMaps**, authored as the reviewable, upstream-contributable artifact. **Executed natively in Python** (in-process transforms), *not* via a JVM FML engine in the hot path — this keeps the runtime in fhirEngine's own language family (TS/Python) with no JVM dependency. An optional **Matchbox/HAPI FML run in CI** executes the same StructureMaps as a *golden oracle* to prove the native implementation matches reference semantics (fidelity without operational JVM).
- **ConceptMaps** for every NEMSIS numeric code set → target system (SNOMED/LOINC/v3 Race/RxNorm-passthrough). The mapper **applies** ConceptMaps *before* submission (NEMSIS-specific translation does not belong in the general-purpose server); it then registers the resulting `ValueSet`s/`CodeSystem`s into fhirEngine (IG-package install + operator terminology load) so the bound codes pass fhirEngine's `$validate-code`. *(fhirEngine exposes `$validate-code`/`$expand`/`$lookup` but not `$translate` — so translation is the mapper's job; adding `$translate` to fhirEngine is an optional upstream contribution, ADR-003.)*
- **NV/PN engine** (cross-cutting): for any nil element, route `NV`→`data-absent-reason` and `PN`→ negation/`statusReason`; escalate section-level emptiness to `Composition.section.emptyReason`.
- **Terminology pass-through**: SNOMED/RxNorm/ICD-10 source codes copied with correct `system` URIs; well-formedness only, not re-coded.

### 5.4 (4) Reference & identity resolver (mapper) — align with fhirEngine MPI
- **Patient identity:** EMS often has only a temporary/unknown identity. Emit `Patient` with a temporary identifier (`use=temp`) plus the NEMSIS `ePatient.01` and UUID as distinct `identifier`s; never fabricate an MRN. This feeds **fhirEngine's deterministic MPI (ADR-0012)**, which does shared-identifier dedup **at promotion**, routing ambiguous matches to `patient_match_review` and writing `patient_link`/merge Provenance in Gold. Probabilistic matching (Splink/PPRL) is an **external pipeline** hook, per fhirEngine — a good home for a future PDQm/PIXm-style matcher.
- **Cross-resource wiring:** resolve `eMedications.09`/`eProcedures.09` crew IDs → `Practitioner`; agency → `Organization`; destination → `Location`/`Organization`; everything → the single `Encounter`. Use **transaction-Bundle `urn:uuid` + conditional references** (fhirEngine resolves `Type?identifier=…` → literal, and honors `ifNoneExist`) so agencies/practitioners/patients aren't duplicated across submissions.
- **Deterministic resource IDs:** UUIDv5 from (PCR UUID + panel + group index + element) → idempotent, diffable re-submissions (a re-converted PCR updates the same ids via conditional update).
- **DS4P tagging is the mapper's job.** fhirEngine *enforces* security labels/consent but states tagging is done **upstream** — so the mapper applies `Composition.confidentiality` and `meta.security` (e.g., 42 CFR Part 2 on substance-use `eHistory.17`) at creation.

### 5.5a (5) Document assembler (mapper)
- Assemble `mPSC-CS` and `mPSC-CR` as `Composition` + `Bundle(type=document)` **from the mapper's own in-memory canonical graph**, in the *same* transaction submission — **do not read resources back from fhirEngine to assemble**, because in `medallion` mode Gold is eventually consistent (a read-after-write race). Section builders are pluggable so proposed sections (Vitals, Procedures, EMS Course) toggle on as they land upstream.
- **Provenance** on every resource: source PCR id + UUID, mapping-ruleset version, ConceptMap versions, mapper version, agent = the converter. Complements fhirEngine's own per-access `AuditEvent` + hash-chained audit (which the mapper does not duplicate).

### 5.5b Validation — two-tier, split across the seam
- **Tier 1 = fhirEngine validation-prior-to-Bronze** (the submission gate): structural + cardinality + terminology bindings + L4 FHIRPath invariants + installed-profile required-elements/bindings/slices. Turn on **US Core 6.1.0 + IPS + mPSC** via `FHIRENGINE_VALIDATION_PROFILES` (installed as IG packages). Invalid resources hit fhirEngine's **resource-level dead-letter** — which becomes a conversion-issue signal.
- **Tier 2 = external HL7 validator** for the authoritative **mPSC/IPS L5 conformance** fhirEngine explicitly *doesn't* do (closed/max slices, discriminators, must-support). Run in CI against the golden corpus; deviations captured in a reviewed allow-list (some unavoidable while mPSC is draft).

### 5.6 (6) Persistence, indexing & serving — **fhirEngine (no new code)**
- Submit the transaction Bundle to fhirEngine `POST /`. fhirEngine handles urn:uuid resolution, validation, **search-index construction** (`repository/search-index.ts`, `ingest.ts`), and **DeltaWarehouse** persistence (delta-rs write / DataFusion read via the Python sidecar), plus history/`vread`/CapabilityStatement. Storage mode: **`single`** for simple/local (read-after-write) or **`medallion`** (Bronze ingest → Gold serving) for scale, with promotion by **Dagster OSS or the `fhirengine-promote` CLI** — **not Spark/Databricks**.

### 5.7 (7) Packaging & transport (thin adapter over fhirEngine)
- For the EMS-Overall handoff, produce a **Provide Document Bundle [ITI-65]/[PCC-1]** from the persisted document — either the mapper wraps the document `Bundle` + `DocumentReference` in an ITI-65 transaction, or an adapter pulls it via fhirEngine `$export`/`read`. Keep transport behind an interface (`ITI-65`, `XDR`, `XDM`, file drop) so direct-to-hospital push vs HIE publish vs media is a config choice (EMS-Overall's binding is deliberately loose; ADR-008).

---

## 6. Terminology strategy (see ADR-003)

1. **Pass-through terminologies** (SNOMED CT, RxNorm, ICD-10-CM, LOINC where already present) — copy code + assign correct canonical `system`; validate structure only.
2. **NEMSIS numeric code sets** — externalize as `ConceptMap`s to standard systems. Where a faithful standard target exists (e.g., route of administration → SNOMED/NCI), map it; where none exists, retain the NEMSIS code via the mPSC `NEMSIS` `CodeSystem` as a secondary coding so nothing is lost. **Dual-coding is the default** (standard + NEMSIS original) to preserve fidelity and enable round-trip.
3. **NV (7701xxx)** → `data-absent-reason` (map `7701001`→`not-applicable`, `7701003`→`unknown`/`not-recorded`, `7701005`→`masked`/`unsupported` — final bindings in the ConceptMap).
4. **PN (8801xxx)** → negation semantics per target resource (statusReason / negated Allergy / negative Observation.interpretation).
5. **Own the `NEMSIS` CodeSystem locally.** The IG's copy has ~13 `TODO`/placeholder concepts and a malformed entry — do not depend on it at runtime. Maintain a clean, versioned local `CodeSystem` + `ConceptMap` set; offer the cleaned version upstream.

---

## 7. Identity, security & compliance — mostly fhirEngine's, by design

The big shift from revision 1: **fhirEngine already provides the security/consent/audit baseline**, so the mapper does not reinvent it. Split of responsibility:

- **fhirEngine enforces:** SMART scopes + JWKS auth, Backend Services (client_credentials + private_key_jwt), UDAP B2B trust, per-access `AuditEvent` + tamper-evident **hash-chained audit**, computable **consent**, **DS4P** security-label enforcement, 42 CFR Part 2 + element-level redaction, hardened TLS, and a **fail-closed production profile** that refuses to boot until auth/audit/transport security are configured. The mapper relies on all of this rather than duplicating it.
- **The mapper tags; fhirEngine enforces.** Because fhirEngine states labeling is done **upstream**, the mapper is the tagger: set `Composition.confidentiality`, `meta.security` (e.g., `R`/`42CFRPart2` on substance-use `eHistory.17`, sensitive impressions), and honor any NEMSIS restriction flags. Get the labels right at creation and fhirEngine does the rest.
- **PHI hygiene in the mapper:** ePCRs are PHI. No PHI in mapper logs — log element *paths*, codes, and PCR ids, never values. `Provenance` must not leak PHI beyond what the resource already carries. Secrets (e.g., `UMLS_API_KEY` for VSAC) injected at deploy, not in code.
- **Local-first deployment fits the home-lab.** fhirEngine is Apache-2.0, runs two containers (TS server + delta-rs sidecar) on a local volume or any object store (S3/GCS/Azure/MinIO/R2). This maps cleanly onto Chad's Ubuntu/Mac-mini + Tailscale setup; the fail-closed prod overlay (`docker-compose.prod.yml`) is the gate before any real PHI.
- **De-identification variant:** for the analytics/quality path, read fhirEngine's **Gold Delta tables with DuckDB** and materialize a de-identified (Safe Harbor) projection as a separate Delta table — the identified operational store (fhirEngine) and the analytic store stay cleanly separated, with no second FHIR engine.

---

## 8. Error handling, data quality & idempotency

- **Never silently drop.** Every unmapped or invalid element lands in a **conversion issue log** with element id, PCR id, reason, and disposition. This log *is* the feedback loop into the mapping workbook's gap register.
- **Quarantine, don't crash.** XSD-invalid records quarantine with a machine-readable `OperationOutcome`; the batch continues.
- **Idempotent re-runs** via deterministic UUIDv5 ids submitted as **conditional updates** in the transaction Bundle; a re-converted PCR updates the same resource ids in fhirEngine (whose Delta layer keeps `is_current` + full `_history`), rather than duplicating. No manual Delta MERGE — fhirEngine owns the write path.
- **fhirEngine's dead-letter is a first-class signal.** Resources that fail validation-prior-to-Bronze are dead-lettered at resource level by fhirEngine; the mapper reconciles that against its own conversion-issue log so a partially-invalid PCR is visible, not silently half-loaded.
- **Golden test corpus:** curated NEMSIS 3.5 sample PCRs (incl. NV/PN edge cases, cardiac arrest, MCI triage, interfacility, pediatric length-based, refusal/no-transport) with expected FHIR output — the regression spine (see roadmap Phase 2).

---

## 9. Runtime comparison (revised: fhirEngine + Delta OSS are now fixed)

Two decisions are now settled, not open: the **FHIR store/server is fhirEngine** (TS/Hono + delta-rs sidecar) and its **backing store is Delta OSS**. Databricks and any Spark/JVM medallion are out. So the only real question is **how the transform executes and reaches fhirEngine** — and the language should stay in fhirEngine's family (TypeScript / Python) to avoid a JVM operational dependency.

| Dimension | **A. Native Python mapper → fhirEngine REST** *(recommended)* | **B. JVM FML sidecar** (Matchbox/HAPI runs StructureMaps at runtime) | **C. Mapper embedded inside fhirEngine** (TS module writing the repo directly) |
|---|---|---|---|
| Fit to fhirEngine (TS/Python) stack | ★★★ Python matches the delta-rs sidecar; XML/terminology are Python-native | ★ adds a JVM service to a TS/Python shop | ★★ same repo, but couples NEMSIS logic into a general server |
| Standards-native / upstream-contributable | ★★★ StructureMaps+ConceptMaps authored as spec; native exec | ★★★ runs the maps literally | ★★ logic tends to drift into TS code |
| SME reviewability | ★★★ maps are the reviewed artifact (this workbook) | ★★★ same maps | ★ buried in server code |
| Uses fhirEngine's validation/persistence/MPI/security | ★★★ via the REST seam — nothing duplicated | ★★★ (still submits over REST) | ★★ tempting to bypass the REST gate |
| Separation of concerns (converter vs server) | ★★★ clean; converter is swappable | ★★ two engines to run | ★ NEMSIS coupling contaminates a reusable server |
| Real-time at-the-door push (future) | ★★★ same mapper behind an HTTP endpoint | ★★ | ★★ |
| Operational simplicity (home-lab) | ★★★ one Python service + fhirEngine's 2 containers | ★ 3 runtimes | ★★ |
| Fidelity assurance | ★★★ CI oracle (option B *in CI only*) proves parity | ★★★ is the reference | ★ |

**Recommendation (ADR-002): Option A — a native Python `nemsis2fhir` mapper that POSTs FHIR transaction Bundles to fhirEngine — with Option B used only as a CI fidelity oracle.** Author the mapping as versioned **StructureMaps + ConceptMaps** (the reviewable, upstream-contributable spec — this workbook is their source of truth), and **execute them natively in Python** so the whole runtime stays TS/Python with no JVM in production. Let **fhirEngine do the heavy FHIR lifting** it already does — validation-prior-to-Bronze, search indexing, Delta persistence, terminology `$validate-code`, MPI dedup, security/consent/DS4P, serving. Run a **Matchbox/HAPI FML execution in CI** against the golden corpus to prove the Python implementation matches reference StructureMap semantics. **Avoid Option C** — embedding NEMSIS-specific logic inside the general-purpose server contaminates a reusable engine and tempts bypassing its own REST validation gate.

> Why not keep FML as the *runtime* engine (old Option B)? It would drag a JVM (Matchbox/HAPI) into a TS/Python deployment for no operational benefit now that fhirEngine — not a mapping engine — owns persistence and validation. FML stays valuable as **spec + CI oracle**, which is where its portability pays off without the runtime tax.

> Practical note: native execution still needs a **thin typed helper layer** for the transforms that are awkward in any declarative map — NV/PN attribute routing, length-based-tape pediatric weight, GCS aggregation, repeating-group correlation. Build these as small, unit-tested Python functions the mapper calls; they are also exactly the transforms the CI FML oracle should scrutinize hardest.

### 9.1 Where Delta OSS lives (since it's fhirEngine's backing store)
- **fhirEngine owns the FHIR Delta tables** (delta-rs write / DataFusion read via its Python sidecar) — `single` mode (read-after-write) for local/dev, or `medallion` (Bronze→Gold, CDF-enabled) for scale, promoted by **Dagster OSS or the `fhirengine-promote` CLI**, never Spark.
- **The mapper owns one extra Delta table**: raw NEMSIS *bronze* (audit/replay of source XML), written with `deltalake` — kept separate from fhirEngine's internal tiers.
- **Analytics/quality** read fhirEngine's **Gold tables directly with DuckDB** (Chad already uses DuckDB over Delta) — no second query engine, no Spark.

---

## 10. Traceability to requirements

- **Layered output** → §4, Layer A then Layer B; the resource graph is the durable asset, the document a projection.
- **Runtime = fhirEngine + Delta OSS, no Databricks** → §5, §9 + ADR-002/009/010: native Python mapper → fhirEngine REST; fhirEngine owns persistence/validation/terminology/MPI/security on Delta OSS; DuckDB for analytics.
- **Complete, upstream-ready superset** → §4.2/§4.4 fill the empty IG cells; §6 cleans the code system; the S2T workbook is the deliverable artifact; proposed sections + cleaned ConceptMaps + an optional fhirEngine `$translate` are the upstream package.
- **Full deliverable set** → this doc, the S2T workbook, the ADRs, and the phased roadmap.

## 11. Key risks & open questions
1. **mPSC instability.** Draft profiles change between branches. *Mitigation:* pin versions; keep Layer B thin; track the mPSC repo.
2. **No home sections for most clinical panels.** *Mitigation:* propose sections upstream (§4.4); until accepted, carry vitals/procedures as `DocumentReference` or in an extension section so nothing is lost.
3. **NEMSIS code system quality.** *Mitigation:* own a clean local copy (§6).
4. **3.5.0 vs 3.5.1 vs CP level** of your actual source feeds — **confirm with the submitting agencies/state**; drives XSD pinning and the `.13`/`.25` sex logic.
5. **US Core vs IPS vs IHE-PCC extension collisions** (race/ethnicity, sex) — reconcile in one validation contract (ADR-006), consistent with your "holistic US Core validation contract" stance.
6. **Outcome loop ownership.** Who runs discharge-summary retrieval and write-back — the engine or a separate service? Deferred (Phase 6) but flagged now.
7. **fhirEngine is pre-alpha.** Real security baseline and broad FHIR surface, but not (g)(10)-certified and synthetic-data-only until the production profile is configured. *Mitigation:* pin a fhirEngine release; enable the fail-closed prod overlay before any PHI; treat its Tier-1 validation as a gate, Tier-2 external validator as authoritative.
8. **No `$translate` in fhirEngine.** ConceptMap execution lives in the mapper. *Mitigation:* accepted (keeps NEMSIS logic out of the server); register resulting ValueSets/CodeSystems so `$validate-code` still gates bound codes; optionally contribute `$translate` upstream.
9. **Medallion eventual consistency.** Reading resources back to assemble the document races Gold promotion. *Mitigation:* assemble the mPSC document from the mapper's in-memory graph in the same transaction (§5.5a); use `single` mode for low-latency handoff paths.
10. **fhirEngine profile validation ≠ L5 IG conformance.** It does required-elements/bindings/first-cut slices, not closed/max slices or must-support. *Mitigation:* the external HL7 validator is the authoritative mPSC verdict (§5.5b).

---
*Companion artifacts: `02_NEMSIS35_to_FHIR_S2T_Mapping.xlsx` (superset mapping), `03_ADRs.md` (decision records), `04_Phased_Roadmap.md` (build plan).*
