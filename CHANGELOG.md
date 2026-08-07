# Changelog

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
