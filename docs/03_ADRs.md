# Architecture Decision Records — nemsis2FHIR
NEMSIS 3.5 → IHE EMS FHIR translation engine
Date: 2026-08-06 · Status of set: Proposed (for review)

Each ADR: Context → Decision → Consequences → Alternatives considered → Status.

---

## ADR-001 — Layered output: canonical resource graph first, mPSC document second

**Context.** The request is to emit IHE-conformant content. But the IHE content IG (mPSC) is v2.0.0-draft with only two published profiles and a four-section IPS Composition that has no home for most clinical panels (no vitals/procedures/EMS-course sections). Its profile set differs between published and `master` builds. Meanwhile the underlying clinical data (vitals, meds, procedures, conditions, allergies) maps cleanly to stable, balloted US Core R4 profiles.

**Decision.** Map NEMSIS → a **canonical, US-Core-aligned FHIR R4 resource graph (Layer A)** as the primary, durable artifact. Assemble the **mPSC IPS Document Bundle (Layer B)** as a thin, swappable projection over Layer A. Validate Layer A against US Core; validate Layer B against mPSC + IPS.

**Consequences.**
- The 90% of effort (field-level mapping) lands in the stable layer and survives mPSC churn.
- When mPSC adds sections/profiles, only the assembly layer changes.
- Two validation contracts to maintain (acceptable; they share the same resources).
- Enables reuse of the resource graph for analytics/quality (gold) independent of the document.

**Alternatives.** (a) *mPSC document only* — tightest conformance but brittle against a moving draft and non-reusable. (b) *Resource graph only* — loses IHE document conformance and the handoff use case. Rejected in favor of layering (which the requester selected).

**Status:** Accepted.

---

## ADR-002 — Native Python mapper → fhirEngine REST; StructureMaps/ConceptMaps as spec + CI oracle (supersedes rev-1 Databricks/Matchbox decision)

**Context.** Revised constraints (rev 2): (1) the FHIR store/server is **fhirEngine** — Chad's OSS TS/Hono server over delta-rs/DataFusion via a Python sidecar; (2) **Delta OSS is fhirEngine's backing store**; (3) **Databricks is removed**; (4) mapping must stay *upstream-ready*; (5) 600+ elements demand SME-reviewable, maintainable logic. fhirEngine already provides validation-prior-to-Bronze, search indexing, Delta persistence, a terminology server (`$validate-code`/`$expand`/`$lookup`, not `$translate`), deterministic MPI, and SMART/UDAP/consent/DS4P — so the transform runtime should *use* fhirEngine, not re-implement it, and should stay in its TS/Python language family (no JVM).

**Decision.** Build a **native Python `nemsis2fhir` mapper** that parses NEMSIS XML, applies ConceptMaps, assembles the canonical resource graph and the mPSC document, and **submits a FHIR transaction Bundle to fhirEngine's REST API**. **Author the mapping as versioned StructureMaps + ConceptMaps** (the reviewable, upstream-contributable spec — the S2T workbook is its source of truth) but **execute it natively in Python**. Use a **Matchbox/HAPI FML run in CI as a fidelity oracle** against the golden corpus. Keep a **thin typed Python helper layer** for transforms awkward in any declarative map (NV/PN routing, GCS aggregation, pediatric length-based weight, group correlation). fhirEngine does all downstream FHIR work.

**Consequences.**
- Whole runtime stays TS/Python — no JVM/Matchbox in production; ops = one Python service + fhirEngine's two containers.
- Mapping artifacts remain standards-native/submittable; the CI oracle proves native exec matches reference StructureMap semantics.
- The mapper is decoupled from and swappable behind the FHIR REST seam; a future real-time at-the-door endpoint reuses the same mapper.
- Cost: we own ConceptMap *execution* (fhirEngine has no `$translate`); mitigated by registering resulting ValueSets/CodeSystems for `$validate-code`.

**Alternatives.** (a) *JVM FML sidecar at runtime (old rev-1 decision)* — drags a JVM into a TS/Python shop for no benefit now that fhirEngine owns persistence/validation; demoted to CI-only. (b) *Mapper embedded inside fhirEngine (TS module writing the repo)* — contaminates a reusable general-purpose server with NEMSIS logic and tempts bypassing its own REST validation gate. Both rejected.

**Status:** Accepted (recommendation). **Supersedes the revision-1 ADR-002.**

---

## ADR-003 — Terminology: dual-coding, ConceptMaps, and explicit NV/PN semantics

**Context.** NEMSIS mixes external terminologies already in the data (SNOMED for impressions/procedures, RxNorm for meds, ICD-10 for some diagnoses) with proprietary numeric code sets, plus two negative-value mechanics: **NV** (7701xxx — no real value + reason) and **PN** (8801xxx — clinically meaningful negative). The mPSC `NEMSIS` CodeSystem is unstable (~13 TODO/placeholder concepts, a malformed entry).

**Decision.**
1. **Pass through** SNOMED/RxNorm/ICD-10/LOINC codes with correct canonical `system`; validate structure, do not re-code.
2. **Externalize** every NEMSIS numeric code set as a versioned FHIR `ConceptMap` to a standard target where one exists; **dual-code** (standard coding + original NEMSIS coding) to preserve fidelity and round-trip.
3. **NV** → `data-absent-reason` extension (not a fabricated value); escalate to `Composition.section.emptyReason` when a whole section is absent (satisfies `ihe-pcc-comp-1`).
4. **PN** → target-appropriate negation (`statusReason`, negated `AllergyIntolerance`, negative `Observation.interpretation`) — **never dropped**.
5. **Own a clean local copy** of the `NEMSIS` CodeSystem; offer the cleaned version upstream.

**Consequences.** No information loss; nils and negatives are semantically preserved; terminology is versioned separately from structure. Requires a terminology-maintenance function and a tx server / `$translate` capability (native to HAPI/Matchbox).

**Alternatives.** Single-coding to standard systems only (loses NEMSIS fidelity/round-trip); treating nils as skips (destroys pertinent negatives — explicit anti-pattern). Rejected.

**Status:** Accepted.

---

## ADR-004 — Encounter as the spine; deterministic identity & references

**Context.** NEMSIS has no first-class encounter object, but every panel is about one prehospital encounter. EMS frequently lacks confirmed patient identity. Re-processing (re-submitting a corrected PCR to fhirEngine) requires idempotency, and fhirEngine has its own deterministic MPI (ADR-0012) that dedups at promotion.

**Decision.**
- Synthesize **one `Encounter` per `PatientCareReport`** as the spine; every clinical resource references it. Populate from `eTimes`/`eResponse`/`eDispatch`/`eDisposition`.
- **Patient identity:** temporary identifier (`use=temp`); carry `ePatient.01` and NEMSIS UUID as distinct `identifier`s; never fabricate an MRN; emit enough demographics for downstream PIXm/PDQm matching.
- **Deterministic resource IDs** via UUIDv5 from (PCR UUID + panel + group index + element), submitted as **conditional updates** so re-submissions update the same ids in fhirEngine (which keeps `is_current` + `_history`) — no manual Delta MERGE; fhirEngine owns the write path.
- Resolve crew/agency/facility references via transaction `urn:uuid` + **conditional references** (`Type?identifier=…`) and `ifNoneExist`, so Practitioner/Organization/Patient aren't duplicated across submissions. Feed fhirEngine's deterministic MPI for cross-PCR patient linkage; leave probabilistic matching (Splink/PPRL) to the external-pipeline hook fhirEngine defines.

**Consequences.** Clean referential graph; safe re-processing via fhirEngine's own history/MPI; provenance-friendly. `CorrelationID` used only for its real purpose (custom-element linkage), not as a global key.

**Alternatives.** Encounter-less flat resources (loses context, breaks US Core Encounter references); random ids (non-idempotent). Rejected.

**Status:** Accepted.

---

## ADR-005 — Conformance target: complete superset, upstream-ready

**Context.** The mPSC NEMSIS→FHIR table is ~90% empty (FHIR-target column populated for ~11 of ~330 rows; `eOutcome` punted to external QORE). The requester chose "complete superset, upstream-ready."

**Decision.** Author a **complete field-level mapping** for all NEMSIS 3.5 national elements, dispositioned as **Mapped / Seeded / Deferred / Upstream-proposed** in the S2T workbook — no silent drops. Structure mapping artifacts (StructureMaps, ConceptMaps, proposed Composition sections, cleaned CodeSystem) so they can be **contributed to IHE PCC / HL7 EMS Work Group**. Align with the existing `dAgency`→`Organization` and `eCustomConfiguration`→`Observation` anchors the IG already provides.

**Consequences.** Larger up-front effort; positions FHIRmedic as a contributor to the standard (strategic, given your EMS WG blood-product concept-paper track). Requires a governance/versioning process for the mapping ruleset.

**Alternatives.** Strict conformance to today's mPSC (fast but drops most clinical data); pragmatic-complete-without-upstreaming (works but forfeits the standards influence). Rejected per requester's selection.

**Status:** Accepted.

---

## ADR-006 — One holistic validation contract (US Core + IPS + mPSC + IHE-PCC extensions reconciled)

**Context.** Race/ethnicity and sex/gender are representable three different ways: US Core extensions, IPS, and the mPSC `pcc-uv-race`/`pcc-uv-ethnicity` extensions. `ePatient.13 Gender` is deprecated in 3.5.0 in favor of `ePatient.25 Sex`. Divergent per-panel validation logic is exactly the siloing you argue against in your day job.

**Decision.** Maintain **one validation contract** with a documented, reviewed deviation allow-list. Layer A validates vs **US Core 6.1.0**; Layer B vs **mPSC + IPS**. Reconcile overlapping extensions explicitly: prefer US Core race/ethnicity/birthsex on the canonical `Patient`, and *additionally* carry mPSC `pcc-uv-*` on the document `Patient` so both conformance targets pass. Map `ePatient.25 Sex` as the source of truth; treat `.13 Gender` as legacy fallback only.

**Consequences.** Predictable, centralized conformance; no per-project validation drift; a single place to reason about extension collisions. Some resources carry redundant-but-valid codings (accepted).

**Alternatives.** Per-layer/per-project validation (drift, duplication); pick-one-extension-standard (fails the other conformance target). Rejected.

**Status:** Accepted.

---

## ADR-007 — Source-version handling: NEMSIS 3.5.0 (CPx) vs 3.5.1, and the sex/gender deprecation

**Context.** 3.5.0 ships as Critical Patches (current ~CP6) and 3.5.1 exists with small differences. `ePatient.13 Gender` deprecated → `ePatient.25 Sex`. The mPSC inventory still lists `.13`. Source agencies may emit any of these.

**Decision.** **Detect the source minor/patch version** at ingest (schema namespace / `eRecord` metadata). Pin XSDs per version. Normalize in the intermediate model: **prefer `ePatient.25`; fall back to `.13`** only when `.25` is absent. Keep a version-conditioned rule table so 3.5.1 deltas are handled as overrides, not forks.

**Consequences.** Robust to a heterogeneous fleet of ePCR vendors/states; no silent mis-mapping of sex. Requires confirming actual source versions with submitting agencies (open question O-4 in the design doc).

**Alternatives.** Assume a single version (fragile); ignore the deprecation (mis-codes sex). Rejected.

**Status:** Accepted, pending source-version confirmation.

---

## ADR-008 — Transport is a pluggable interface (ITI-65 default), not a hard binding

**Context.** EMS-Overall deliberately leaves transport loose (MHD/ITI-65, XDR, XDM, XDS publish, MHDS all named; no ITI numbers pinned). mPSC requires only its own [PCC-1] with no required actor groupings.

**Decision.** Implement **Provide Document Bundle [ITI-65]** as the default packaging, behind a **transport interface** with adapters for XDR (point-to-point push), XDM (media), and file drop. Deployment selects the adapter by config.

**Consequences.** Matches the spec's looseness; lets the same engine serve direct-to-hospital push, HIE publish, or media hand-off without core changes.

**Alternatives.** Hard-wire one transport (breaks under the varied real-world exchange topologies EMS-Overall anticipates). Rejected.

**Status:** Accepted.

---

## ADR-009 — fhirEngine is the FHIR system of record, with Delta OSS as its backing store

**Context.** Rev 2 fixes the FHIR repository as **fhirEngine** (Chad's OSS server) with **Delta OSS** as its persistence layer (delta-rs write / DataFusion read via a Python sidecar). fhirEngine ships validation-prior-to-Bronze, search indexing, history/versioning, a terminology server, deterministic MPI, SMART/UDAP auth, consent + DS4P enforcement, tamper-evident audit, and `single|medallion` storage — a large surface the converter must not duplicate.

**Decision.** The `nemsis2fhir` mapper produces **FHIR transaction Bundles and submits them over fhirEngine's REST API**; fhirEngine is the sole writer of the FHIR Delta tables and the system of record. The mapper keeps exactly **one** Delta table of its own — raw NEMSIS bronze (source audit/replay) — separate from fhirEngine's internal tiers. Storage mode is an install choice: **`single`** (read-after-write) for local/handoff-latency paths, **`medallion`** (Bronze→Gold, CDF) for scale, promoted by **Dagster OSS or the `fhirengine-promote` CLI**. Analytics read fhirEngine's **Gold tables with DuckDB**.

**Consequences.**
- No second FHIR engine, no duplicated validation/persistence/security; one storage substrate (Delta OSS).
- The converter is thin and swappable behind the REST seam.
- Constraint inherited: fhirEngine profile validation is not full L5 (→ external validator is authoritative, ADR-006); `medallion` Gold is eventually consistent (→ assemble documents from the mapper's in-memory graph, not read-back); fhirEngine is pre-alpha (→ pin a release, enable fail-closed prod profile before PHI).
- DS4P/consent **tagging** is the mapper's responsibility (fhirEngine enforces, does not tag).

**Alternatives.** (a) Mapper writes FHIR Delta tables directly (bypassing fhirEngine) — loses validation, indexing, MPI, security, and history; rejected. (b) A different FHIR server — contradicts the requirement to use fhirEngine. Rejected.

**Status:** Accepted.

---

## ADR-010 — No Spark / no Databricks; delta-rs + DuckDB + fhirEngine-native promotion

**Context.** Rev 1 assumed a Databricks/Spark medallion. Rev 2 removes Databricks and standardizes on OSS Delta. Chad's environment already uses **DuckDB over local Delta**; fhirEngine already integrates **delta-rs/DataFusion** and supports promotion via **Dagster OSS or its `fhirengine-promote` CLI**.

**Decision.** Eliminate Spark/Databricks from the design. Writes go through **delta-rs** (mapper's raw-NEMSIS bronze; fhirEngine's FHIR tables via its sidecar). Batch orchestration is plain Python jobs (optionally Dagster OSS); medallion promotion uses **`fhirengine-promote`/Dagster**, never Spark. Analytics/quality use **DuckDB** over Delta Gold. Scale is handled by concurrency + fhirEngine's medallion mode, not a cluster.

**Consequences.**
- Runs entirely on Chad's home-lab footprint (Ubuntu/Mac-mini, containers, object store optional) with no cluster or vendor lock-in.
- Simpler ops and lower cost; upper bound on throughput is single-node/concurrency rather than Spark elasticity — acceptable for EMS PCR volumes; revisit only if a very large state-registry backfill demands it.
- Consistent tooling with fhirEngine's own stack.

**Alternatives.** Keep Spark for batch scale (reintroduces the platform we were asked to drop; over-provisioned for the data volume). Rejected.

**Status:** Accepted.
