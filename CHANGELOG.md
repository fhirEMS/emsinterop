# Changelog

## Unreleased

- **Canonical base is now `https://emsinterop.com/fhir`** — an owned domain
  rather than a hosting vendor's subdomain, because a canonical is a permanent
  identifier baked into every emitted extension URL. Never released under the
  interim `fhirems.github.io` base, so nothing downstream is affected.
- **`scripts/build-canonical-site.py` + a Pages workflow** now serve all 224
  canonicals: HTML at the canonical for a human, `<canonical>.json` for a tool,
  and the authored FML alongside each StructureMap. Generated from the same
  builder as the released package, so the site and the package cannot drift. A
  test and a workflow step both fail if any minted canonical lacks a page.

- **Conformance/gap policy (`src/emsinterop/conformance.py`,
  `docs/07_Conformance_and_Gaps.md`).** Where the IHE EMS profiles are silent
  this project decides; those decisions are now *declared* rather than blended
  into conformance. Two rules, both enforced by `tests/test_conformance.py`:
  reference other people's canonicals but never publish at them, and canonical
  URLs resolve while naming systems need not.
- **Fixed canonical squatting on the mPSC NEMSIS CodeSystem.** The
  `emsinterop.nemsis` package published 2,321 concepts at
  `https://profiles.ihe.net/PCC/mPSC/CodeSystem/NEMSIS` — the identifier where
  IHE publishes 18 `TODO: JFM` placeholders. Two conflicting definitions of one
  canonical break whichever terminology server loads ours second. The package
  now publishes under our own canonical and records, via `identifier` and a
  description, which canonical it stands in for. **Emitted codings are
  unchanged** — they still reference the mPSC canonical, so our data becomes
  conformant the day the IG is fixed, with no migration.
- **Authored canonicals moved to a resolvable base**
  (`https://fhirems.github.io/emsinterop/fhir`), from unresolvable
  `urn:emsinterop:*`. Affects the `obtained-prior-to-unit-care` extension URL in
  emitted resources (hence the ruleset bump), plus ConceptMaps, StructureMaps
  and logical models. Old URNs are retained as `identifier` entries for one
  release. **Identifier naming systems are deliberately unchanged**:
  `urn:emsinterop:resource-id` is embedded in every conditional-update URL, so
  moving it would fail to match already-stored resources and duplicate them.
- **Seven-entry gap register**, each with a citable source, an ISO verification
  date and — the part usually missing — a retirement trigger. A local decision
  with no retirement trigger is a permanent fork wearing a temporary label. It
  ships in the terminology package manifest under `emsinterop:conformance`.
- **`MAPPING_RULESET_VERSION` bumped to 0.3.3** for the emitted extension URL.

- **`tests/test_corpus_coverage.py`** — the honest denominator for every "0
  findings" the sweep reports. When the sweep first came back clean across
  20,000 cases, measurement showed only **19 of 83 national elements (22%)**
  ever carried a real value; the rest were nil+NV, so the mapper's handling of
  them never executed. nemsynth now populates **93%**, and this test holds that
  floor and requires every unpopulated element to be a documented decision
  (`eOutcome.01/.02` come from the inbound outcome loop, not from a crew at the
  time of the call) rather than an oversight.

## v0.3.3 — 2026-08-10

### Fixed

- **Symptom onset is no longer dropped when there is no impression.**
  `eSituation.01` (national, Required) was read *inside* the primary-impression
  branch, so a record whose impression was NV/PN never even looked at it — the
  time the patient's symptoms began vanished with no ledger entry, breaching the
  never-silently-drop rule. Onset is now resolved once and carried by whichever
  Condition exists (impression or chief complaint); with neither, it survives as
  a standalone dated Observation, the shape `eSituation.18` (Last Known Well)
  already used. `eSituation.07`/`.08` had the identical defect — read only
  inside the chief-complaint branch — and are now resolved up front too, with an
  explicit deferral when no Condition exists to carry an anatomic location.

  Found by generated volume, not by hand: 300 documents from
  [nemsynth](https://github.com/fhirEMS/nemsynth) at `--messiness high` reached
  a branch combination that neither the six hand-authored fixtures nor the five
  published NEMSIS samples contained. Distilled into
  `tests/fixtures/hostile/hostile_onset_no_impression.xml` so default CI holds
  it permanently.

- **The sample discovery tier scopes itself by namespace.** It globs `*.xml` so
  it can consume generated corpora as well as published samples; a pointed-at
  directory holding unrelated XML previously failed the tier. Non-NEMSIS files
  are now excluded *and named* in the skip reason rather than silently ignored.

### Added

- **Corpus sweep (`python -m emsinterop.fuzz`).** Generates NEMSIS at volume via
  nemsynth, converts it, and triages the results: findings deduplicate to a
  stable signature, each carries a byte-reproducible replay command, and the
  run fails only on signatures absent from `tests/fuzz-baseline.json`. A
  20,000-case sweep across 15 scenarios, 4 messiness profiles, both releases
  and MCI datasets reports 0 findings; the baseline is empty on purpose.

  Half the cases pair with a generated **DEMDataSet** roster. The agency name
  lives only there, so without one every `Organization` withholds its US Core
  claim and that branch went unswept; an agency that reports no name is the
  other real-world branch, and the one a consumer gets wrong by turning absence
  into an empty string.

- **`emsinterop.invariants`** — the rules that must hold of any conversion, in
  one place, shared by the sweep and the hostile-fixture tier so they cannot
  drift. Adds a reference-closure rule nothing previously checked: a dangling
  relative reference survives JSON validity and profile checks all the way to
  a server. `tests/test_invariants.py` proves every rule can actually fire —
  a rule that cannot fail is worse than no rule.

### Changed

- **`MAPPING_RULESET_VERSION` bumped to 0.3.2.** It is stamped into every
  resource's `meta.tag` and into Provenance, and the convention is to bump on
  mapping semantics rather than package version. The onset fix adds a resource
  to the output, so a consumer must be able to tell which rules produced what
  it is holding.

## v0.3.2 — 2026-08-10

- **NEMSIS 3.5.1 supported.** Its XSDs are vendored and `validate()` selects the
  schema set from the release each document declares. The delta from 3.5.0 was
  established by fetching all 46 XSDs from NEMSIS's public git and diffing them
  (line endings masked everything until normalized): exactly one line differs —
  `ePatient.25` gains an explicit `minOccurs="1"`, which is XSD's default and so
  a no-op. A test validates the whole corpus against every supported release
  rather than assuming compatibility. Unknown future releases fall back to the
  pinned schemas so a real difference surfaces as an error.
- **Hour-24 timestamps normalized.** `xs:dateTime` permits `24:00:00` as
  end-of-day and NEMSIS allows it, but FHIR caps hours at 23 — so an XSD-valid
  export produced FHIR every validator rejects. Now shifted to `00:00:00` the
  next day (the same instant), correct across month and year rollovers, applied
  at all eleven dateTime copy sites. Previously a documented limitation.
- **Unreachable endpoints no longer crash the CLI.** A configured but
  unreachable fhirEngine raised a raw `ConnectError` traceback out of
  `dispatch()`. Transport failures are now reported as a failed delivery,
  ledgered for the gap register, and exit non-zero — distinct from a
  `SubmissionError`, where the server evaluated the bundle and rejected it.
- **Setup path for rail selection**: `deploy/messaging.example.json` (a starter
  that runs out of the box — no endpoints, so artifacts are produced and
  reported rather than delivered) plus a README section walking copy → edit
  `mode` → `--config`. Tests assert the shipped templates parse and select
  rails, so they cannot rot.
- **README reframed** around what this actually is: a poly-HL7 engine emitting
  HL7 v2, C-CDA, and/or FHIR R4 — whichever the administrator configures.
- **contrib policy is now absolute**: nothing goes to IHE or any third party
  without express permission for that specific submission, across every channel.

## v0.3.1 — 2026-08-09 — field hardening

The first release driven by **real** NEMSIS data. Running five published v3.5.0
scenario samples exposed defects six self-authored fixtures never could: one
crashed the converter, one destroyed a reading silently, and two produced
documents the official HL7 validator rejected.

- **New hostile corpus** (`tests/fixtures/hostile/`, `test_hostile_corpus.py`,
  default CI): XSD-*valid* input that broke us once. Plus an env-gated
  discovery tier (`EMSINTEROP_SAMPLES`) for the external samples themselves.
- **Silent data loss fixed**: a comment inside a valued element made it parse
  as an empty group and the reading vanished with no ledger entry — lxml counts
  comments as children, and puts following text in the comment's tail.
- **Untrusted-input hardening**: new `ingest/safexml.py` (no entity resolution,
  no DTD, no network, doctype rejected) closes XXE and entity-expansion on the
  push endpoint; a non-XML body now quarantines as 422 instead of a 500
  traceback; `max_body_bytes` caps attacker-declared CONTENT_LENGTH (413).
- **Conformance, and absence carried faithfully**: an undated vital is
  expressed at the encounter's **date** precision (FHIR `dateTime` is
  variable-precision) rather than a fabricated timestamp. Where nothing is
  derivable — an unrecorded or refused **sex** — `cm-nemsis-sex` now maps the
  NV/PN codes to `administrative-gender#unknown`, FHIR's own "the gender is not
  known". Those rows are `equivalence=wider`, so a reverse mapping can never
  resurrect "Refused" from `unknown`, and the precise NEMSIS code stays in the
  issue ledger. This matters beyond the one field: `us-core-patient` requires
  `gender`, and US Core requires every `subject` reference to point at a
  `us-core-patient`, so an absent gender cost the WHOLE document its
  conformance. Where a value genuinely cannot be derived, the primitive carries
  the **standard** `data-absent-reason` extension — no bespoke extension, which
  would validate nowhere until the consumer loads our StructureDefinition. Off-scale glucose (`High`/`Low`) becomes interpretation
  `>` / `<` ("above/below the maximum quantifiable limit"), not a data fault.
- **Identity**: PCR UUIDs are case-normalized — a re-export with different
  casing previously produced different ids and duplicated instead of updating.
  Conditional-update URLs escape identifier values.
- **Outcome rail**: `apply_outcome` re-validates its own output and refuses to
  emit an XSD-invalid document to a state registry; mixed naive/aware
  timestamps report unavailable instead of raising; short HL7 DTMs no longer
  become month/day `00`; non-NUBC discharge codes are no longer written into
  NUBC-enumerated fields.
- **Numerics**: `nan`/`Infinity`/`1e400`/`1_0` are rejected — they serialize as
  bare `NaN`, which is invalid JSON and made the entire bundle unparseable.

`MAPPING_RULESET_VERSION` is now `0.3.1` (stamped in every resource's
`meta.tag`) because mapping semantics changed. `__version__` now reads from
installed metadata rather than drifting on its own.

**Id-affecting:** the UUID normalization changes deterministic ids for any
record previously ingested with a non-lowercase `PatientCareReport/@UUID`.
Those submit once more as new ids, then remain stable. The golden corpus is
unaffected (all six already carry canonical lowercase UUIDs).

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
