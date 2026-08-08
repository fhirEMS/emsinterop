# Changelog

## v0.3.0 — 2026-08-08 — **alpha**

First release with every roadmap phase (P0–P7) implemented. Additive over the
0.2 line: no breaking changes to the downstream compatibility surface
(`MappingContext`, `convert()`/`ConversionResult`, corpus layout).

**Phase 5 — operations & governance**

- **Dead-letter reconciliation** (`emsinterop reconcile <bronze> <delta-base>`):
  replays raw-NEMSIS bronze, re-converts, and joins fhirEngine's
  `deadletter/<type>` Delta tables (read-only) back to PCRs by deterministic
  resource id or PCR business identifier — the gap-register feed. The
  conversion issue log now persists (`IssueLog.write_jsonl` / `read_jsonl`,
  `convert --issues-out`), and submit-time rejections fold into it: fhirEngine
  rejects transactions *atomically*, so a rejected PCR never reaches the
  server-side dead-letter and its `OperationOutcome` is the only record.
  `--submit` and `--config` dispatch now exit non-zero on failure.
- **PHI-safe structured logging** (`emsinterop.log`): `event()` enforces
  metadata-only output through a field allowlist — non-allowlisted fields are
  dropped by name, never by value — so a call site cannot leak a patient value.
  `NullHandler` on the library root; instrumented at the convert/submit/bronze/
  dispatch seams. Corpus-wide test asserts no fixture PHI reaches DEBUG logs.
- **`emsinterop.nemsis` FHIR package** (`emsinterop package-ig <dir>`): the local
  clean NEMSIS registry as a CodeSystem (2,321 concepts, `content=fragment`)
  plus 205 per-element ValueSets and the authored ConceptMaps/extension/logical
  models — installable into fhirEngine via `fhirengine-terminology install-ig`,
  so dual-coded NEMSIS codings pass `$validate-code`. `scripts/tier1-up.sh`
  installs it alongside US Core 6.1.0.
- **Safe-Harbor de-identified analytics** (`emsinterop deid <delta-base> <out>`):
  reads fhirEngine's Gold (Bronze fallback) Delta tables via DuckDB and
  materializes flattened `encounters`/`vitals` tables, de-identified by
  *construction* — salted-hash pseudonyms (stable `--salt` for cross-run
  linkage), year-only dates, ages capped at 90, state + ZIP3 with the 17
  restricted prefixes nulled. Names/addresses/telecoms/identifiers are never
  projected.
- **Release CI + runbook**: tag-triggered workflow builds and attaches the
  terminology package (refusing a version/tag mismatch); `docs/05_Operations.md`
  documents prod gates, provisioning, the steady-state pipeline, promotion,
  de-id cadence, and releases. DS4P labels and NEMSIS terminology are now
  asserted end-to-end in the Tier-1 harness.

**Phase 6 — the outcome loop closes**

- **FHIR Discharge Summary rail**: a hospital discharge document (LOINC 18842-5)
  reduces to the same transport-neutral `OutcomeRecord` as ADT^A03, so the
  conservative three-signal matcher and XSD-order-preserving eOutcome write-back
  are shared. `emsinterop outcome` sniffs ER7 vs JSON.
- **Reverse mapping** (FHIR → NEMSIS): `reverse_translate()` runs the authored
  ConceptMaps backwards, reversing only `equivalent`/`equal` rows — a `wider`
  row must not reverse, as it would fabricate precision the source never
  asserted. `patient_to_nemsis()` recovers the demographics panel; corpus
  round-trip tested.
- **At-the-door push endpoint** (`emsinterop serve`): stdlib WSGI; `POST /push`
  runs the batch pipeline synchronously (XSD → optional bronze landing →
  convert → per-rail dispatch), so with fhirEngine in `single` mode the
  encounter is queryable the moment the push returns. 422 + `OperationOutcome`
  for invalid XML, 502 when a configured rail fails; delivery summaries only —
  artifacts and resource content are never echoed back.

**Phase 7 — upstream contribution**

- `contrib/`: the completed 212-row NEMSIS→FHIR field map exported from the S2T
  workbook (`scripts/export-fieldmap.py`), a gap report re-verified against the
  live mPSC v2.0.0-draft CI build, and six channel-neutral proposal documents.
  No issues are filed in third-party repositories; the delivery channel is the
  maintainer's decision.

**Repository.** Canonical home is now <https://github.com/fhirEMS/emsinterop>.
Git-URL installs and the `nemsis2ccda` pin comment point there; update any local
remote with `git remote set-url origin https://github.com/fhirEMS/emsinterop.git`.

**Compatibility.** Downstream consumers pinning `emsinterop>=0.2.0,<0.3` should
widen to `<0.4` — the surface is unchanged, the cap is what needs moving.

## v0.2.0 — 2026-08-07

**Renamed: nemsis2fhir → emsInterop** (package `emsinterop`). The engine now
speaks three standards (FHIR R4/mPSC, HL7 v2 ADT, C-CDA via nemsis2ccda) plus
the inbound outcome loop — the old name undersold it. Breaking for consumers:

- Python package/imports: `nemsis2fhir` → `emsinterop`; CLI `python -m emsinterop`
- Env vars: `NEMSIS2FHIR_*` → `EMSINTEROP_*` (TIER1_URL, TIER2, FML_ORACLE,
  VALIDATOR_JAR, CCDA corpus vars)
- Identifier/URN systems: `urn:nemsis2fhir:*` → `urn:emsinterop:*` (conditional
  PUT upserts key on the new system; wipe or migrate any dev fhirEngine store)
- GitHub repo: FHIRmedicConsulting/emsInterop (old URLs redirect)

Also new since v0.1.0: MessagingConfig deployment rails (`mode: fhir | adt |
ccda`, lists, legacy `both`/`all`), `--config` CLI dispatch with delivery
report, and the C-CDA rail via the optional nemsis2ccda package (now nested
at `./nemsis2ccda` as its own repo, gitignored here).

## v0.1.0 — 2026-08-07

First tagged release. The complete NEMSIS 3.5.0 → FHIR R4 translation engine:

- **Ingest**: XSD-validated parsing against pinned NEMSIS 3.5.0 schemas with
  NV/PN and `xsi:nil` first-class; DEMDataSet demographics (agency roster);
  raw-NEMSIS bronze Delta table with hash-idempotent landing and
  byte-identical replay.
- **Canonical graph (Layer A)**: US-Core-aligned mappers for every national
  panel; never-silently-drop coverage sweep (test-enforced); NV →
  data-absent-reason, PN → negation semantics; deterministic UUIDv5 ids;
  DS4P tagging; Provenance.
- **Terminology**: local clean NEMSIS code registry (205 elements); 7 authored
  ConceptMaps executed in-mapper with dual-coding; XSD-verified terminology
  reality (eSituation.09–.12/eHistory.08 are ICD-10-CM).
- **Documents (Layer B)**: mPSC Composition + reference-closure document
  bundle (CR/CS variants); ITI-65 Provide Document Bundle (0 errors vs
  ihe.iti.mhd#4.2.2) with pluggable transports.
- **Submission**: conditional-PUT upsert transactions to fhirEngine
  (idempotent resubmission).
- **Verification**: 6-case golden corpus; Tier-1 (live fhirEngine, US Core
  declared-profile enforcement); Tier-2 (official HL7 validator, 0 errors);
  FML fidelity oracle (5 StructureMaps + 5 logical models vs the reference
  Java engine).
- **Spec artifacts** (`maps/`): ConceptMaps, StructureMaps, logical models,
  prior-to-unit-care extension — the upstream-contributable set.

The C-CDA projection lives in the sibling repo
[nemsis2ccda](https://github.com/FHIRmedicConsulting/nemsis2ccda) (split from
this repo at this release with full history), consuming this package's Layer A.

**Compatibility surface for downstream consumers** (nemsis2ccda): the
`MappingContext` API (`resources`, `pcr`, `header`, `rid()`, `agency_names`),
`convert()`/`ConversionResult`, and the golden corpus layout
(`tests/fixtures/pcr_*.xml`). Breaking changes to these bump the minor version
pre-1.0 and get a heads-up to downstream admins.
