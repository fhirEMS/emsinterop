# CLAUDE.md — emsInterop

Guidance for Claude Code working in this repo. Read `docs/01_Architecture_Design.md` and
`docs/03_ADRs.md` before writing code; this file is the fast orientation.

## What this project is
A translation engine that converts **NEMSIS v3.5 ePCR XML** into **IHE-conformant FHIR R4** and
loads it into **fhirEngine** (Chad's OSS FHIR R4 server, sibling repo at `../fhirEngine`).

**It is built.** As of **v0.3.0 (alpha)** every roadmap phase P0–P7 is implemented: ingest,
canonical mapping, mPSC documents, HL7 v2 ADT, C-CDA (sibling `nemsis2ccda`), submission,
transport, the outcome loop, ops tooling, and the upstream contribution package. `docs/` is
still the specification — read it before changing behavior — but treat the code as the
current truth and keep the two in sync. Remaining work is field hardening, not phase work
(see the README's "Scope & limitations"). The suite is `python -m pytest` (187 passing;
Tier-1/Tier-2/FML-oracle tiers are env-gated skips).

## The one framing that governs everything
"The IHE EMS spec" is two IGs:
- **IHE EMS-Overall** (`ihe.pcc.ems-overall`) — umbrella workflow (actors, ITI document-sharing,
  ITI-65 handoff). Almost no computable content.
- **IHE PCC mPSC** (`ihe.pcc.mpsc`) — the content IG (IPS-based `Composition`, `NEMSIS` code
  system). Its NEMSIS→FHIR table is **~90% empty** — we author the field mapping ourselves.

So the target is **layered**: map NEMSIS → a **canonical US-Core-aligned FHIR R4 resource graph**
first (the durable 90%), then **assemble the mPSC IPS document** as a thin projection over it.

## Architecture in one paragraph (see ADR-002/009/010)
A **native Python mapper** (this repo) parses NEMSIS XML, applies ConceptMaps, builds the canonical
resource graph **and** the mPSC document in one pass, and **submits a FHIR transaction Bundle to
fhirEngine's REST API**. fhirEngine (`../fhirEngine`, TS/Hono + delta-rs/DataFusion Python sidecar)
owns validation-prior-to-Bronze, search indexing, **Delta OSS** persistence, terminology
`$validate-code`, deterministic MPI, security/consent/DS4P, and serving. **No Databricks, no Spark,
no JVM in production.** DuckDB reads fhirEngine's Gold Delta tables for analytics.

## Hard rules (do not violate without an ADR)
- **Never write FHIR resources to Delta directly.** The only writer of FHIR tables is fhirEngine,
  over its REST API. The mapper's only own Delta table is raw-NEMSIS bronze (source audit/replay).
- **No JVM/Matchbox in the runtime.** StructureMaps + ConceptMaps are the authored *spec* and a
  **CI-only** fidelity oracle (Matchbox/HAPI). Execution is native Python.
- **Never silently drop a NEMSIS element.** Every element is Mapped / Seeded / Deferred per the
  workbook. Unmapped/invalid → conversion issue log (reconciled against fhirEngine's dead-letter).
- **NV/PN are first-class, never nil-skipped.** `NV` (7701xxx) → `data-absent-reason` (+ section
  `emptyReason`); `PN` (8801xxx) → negation/`statusReason`/negated resource. A converter that
  treats `xsi:nil` as "skip" destroys pertinent negatives — this is the #1 correctness trap.
- **Repeating group → one resource per instance, sharing the group's `.01` timestamp**
  (VitalGroup → N Observations @ eVitals.01; MedicationGroup → MedicationAdministration @
  eMedications.01; ProcedureGroup → Procedure @ eProcedures.01).
- **Assemble the mPSC document from the mapper's in-memory graph**, submitted in the *same*
  transaction — do **not** read resources back from fhirEngine (medallion Gold is eventually
  consistent).
- **ConceptMap execution lives here**, not in fhirEngine (it has `$validate-code`/`$expand`/
  `$lookup` but **no `$translate`**). Dual-code (standard + original NEMSIS) to preserve fidelity;
  register resulting ValueSets/CodeSystems into fhirEngine so bound codes pass `$validate-code`.
- **Encounter is the spine** — one `Encounter` per `PatientCareReport`; everything references it.
- **Sex:** prefer `ePatient.25 Sex`; `ePatient.13 Gender` is deprecated in 3.5.0 (legacy fallback).
- **The mapper tags DS4P/security labels** (fhirEngine enforces but expects upstream tagging).

## Structure (as built)
```
src/                 # Python mapper
  ingest/            # XML load → raw-NEMSIS Delta bronze (deltalake); XSD/Schematron validate
  model/             # typed intermediate model (NV/PN preserved as first-class fields)
  mapping/           # per-panel canonical mappers (StructureMaps authored in maps/, executed here)
  terminology/       # ConceptMap application; NV/PN engine; ValueSet/CodeSystem builders
  assemble/          # mPSC-CS / mPSC-CR Composition + document Bundle builders
  submit/            # transaction Bundle builder + fhirEngine REST client
  transport/         # ITI-65 / XDR / XDM / file adapters
  outcome/           # inbound loop: ADT^A03 + FHIR Discharge Summary → match → eOutcome
  analytics/         # Safe-Harbor de-id projection over fhirEngine Gold (DuckDB read)
  config.py          # MessagingConfig rails (fhir | adt | ccda) + dispatch()
  serve.py           # at-the-door push endpoint (WSGI)
  reconcile.py       # issue log ↔ fhirEngine dead-letter → gap register
  log.py             # PHI-safe structured logging (field allowlist)
maps/                # StructureMaps (FML) + ConceptMaps — the upstream-contributable spec
tests/               # golden corpus (NV/PN, arrest, MCI, interfacility, peds, refusal) + harness
docs/                # the specification (start here); 05_Operations.md is the runbook
contrib/             # IHE PCC mPSC contribution package (field map, gap report, proposals)
nemsis2CCDA/         # sibling repo, nested + gitignored: the C-CDA rail
```
Language: **Python** (matches fhirEngine's sidecar; lxml/pydantic/deltalake/duckdb). TS is fine for
any thin service colocated with the server, but the mapper is Python.

## Build order (historical — all phases delivered in v0.3.0)
P0 foundations → P1 ingest/parse/validate → P2 golden corpus + harness → P3 canonical mapper →
P4 document assembly → P5 packaging/transport/ops → P6 outcome loop → P7 upstream contribution.
Kept for context on *why* the code is shaped this way; new work is field hardening, so start
from the code and `CHANGELOG.md` rather than the phase plan.

## Definition of done for a panel
Every element dispositioned in `docs/02_..._S2T_Mapping.xlsx`; golden-corpus cases green through
fhirEngine Tier-1 validation **and** the external HL7 validator (Tier-2, authoritative for mPSC);
Provenance emitted; NV/PN cases covered.

## Open items to confirm with Chad
- Exact source NEMSIS minor/patch (3.5.0 CP-level vs 3.5.1) — drives XSD pinning + sex logic.
  (Pinned to 3.5.0 today; 3.5.1 deltas handled as overrides but not corpus-tested.)
- Whether to add `$translate` to fhirEngine (optional upstream contribution).
- Production PHI enablement — needs fhirEngine's fail-closed profile and a DS4P/consent
  review (`docs/05_Operations.md` §1). Until then: **synthetic data only.**

## Standing constraints
- **Never publish anything to IHE — or any third party — without Chad's express
  permission, per submission.** This is absolute and covers every channel, not just
  GitHub: no issues, no PRs, no email, no public comment, no chat.fhir.org post, no
  handing material to an intermediary. `contrib/` is a KEPT-SEPARATE working set, not
  a queue awaiting dispatch; "it was ready" is never authorization. Standing consent
  does not exist here — permission is per submission, and silence is not permission.
- Local dev gotcha: after any `pip install -e`, pip-written `__editable__*.pth` files are
  silently ignored on this Mac — rewrite them in place, or use `PYTHONPATH=src`.
