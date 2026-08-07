# nemsis2fhir

A translation engine converting **NEMSIS v3.5 EMS Patient Care Report (ePCR) XML** into
**IHE-conformant FHIR R4** (IHE PCC mPSC / US Core), loaded into
[**fhirEngine**](../fhirEngine) on OSS Delta Lake. No Databricks, no Spark, no JVM.

> **Status:** design complete, greenfield code. The `docs/` folder is the specification.
> Start with `docs/01_Architecture_Design.md`, then build in the order of `docs/04_Phased_Roadmap.md`.

## How it works (short version)
NEMSIS XML → a native **Python mapper** (this repo) that parses, applies ConceptMaps, and builds a
canonical FHIR R4 resource graph **and** the mPSC IPS document → **submitted as a FHIR transaction
Bundle to fhirEngine's REST API**. fhirEngine validates, indexes, persists to Delta, and serves.
DuckDB reads Gold tables for analytics.

```
NEMSIS 3.5 XML ─▶ nemsis2fhir (Python: parse → map → ConceptMaps → assemble mPSC)
                        │  FHIR transaction Bundle (POST /)
                        ▼
                  fhirEngine (../fhirEngine) ── Delta OSS ── DuckDB (analytics)
                        │
                        ▼  Provide Document Bundle [ITI-65] / [PCC-1]  (handoff)
```

## Getting started (dev)

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest                       # golden-corpus + unit tests
.venv/bin/python -m nemsis2fhir validate tests/fixtures/pcr_chest_pain.xml
.venv/bin/python -m nemsis2fhir convert tests/fixtures/pcr_chest_pain.xml --issues
.venv/bin/python -m nemsis2fhir convert tests/fixtures/pcr_chest_pain.xml --submit http://localhost:8080
```

Layout: `src/nemsis2fhir/` (ingest → model → mapping → terminology → assemble →
submit), `maps/conceptmaps/` (authored FHIR ConceptMaps — the upstream-contributable
spec), `schemas/nemsis/3.5.0/` (pinned NEMSIS XSDs), `tests/fixtures/` (XSD-valid
golden corpus).

### Tier-1 validation (live fhirEngine)

`scripts/tier1-up.sh` boots the sibling fhirEngine (dev profile, synthetic data
only) with US Core 6.1.0 installed and `FHIRENGINE_VALIDATION_PROFILES=declared`,
then the env-gated harness submits the whole corpus and proves idempotent
resubmission:

```bash
./scripts/tier1-up.sh &   # sidecar + server + US Core install
NEMSIS2FHIR_TIER1_URL=http://127.0.0.1:8095 .venv/bin/python -m pytest tests/test_tier1_fhirengine.py -v
```

Submission uses **conditional PUT upserts** (`PUT Type?identifier=urn:nemsis2fhir:resource-id|…`)
because fhirEngine deliberately has no update-as-create; its conditional update
creates on 0 matches (preserving our deterministic client ids, so literal
references hold) and updates in place on 1 match. Agency display names (absent
from the EMSDataSet header) are supplied via `convert(..., agency_names={...})`;
without one the Organization ships `_name` data-absent and withholds its US Core
claim.

### Tier-2 validation (official HL7 validator — authoritative)

The whole corpus's mPSC document bundles pass the official validator with
**0 errors** against base R4 + US Core 6.1.0 + this repo's authored
StructureDefinitions:

```bash
./scripts/tier2-validate.sh          # java 17+ and ~/Downloads/validator_cli.jar
NEMSIS2FHIR_TIER2=1 .venv/bin/python -m pytest tests/test_tier2_validator.py
```

The document bundle is a **projection**: the reference closure from the
Composition (plus Provenance, targets trimmed to members), deep-copied with all
internal references rewritten to `urn:uuid:` form as FHIR document resolution
requires. Operational resources no section claims (PractitionerRole) stay in
the transaction only. mPSC/IPS profile-level validation is deferred until a
pinnable (non-draft) mPSC package exists.

### Raw-NEMSIS bronze (audit/replay — the mapper's ONE Delta table, ADR-009)

`python -m nemsis2fhir land <xml> <table>` shreds an EMSDataSet into the raw
bronze Delta table (`deltalake`, one row per PCR stored as a self-contained
single-PCR document with its header). Landing is **idempotent by file sha256**;
`ingest.bronze.replay()` returns payloads that XSD-validate and convert to
**byte-identical FHIR** (same deterministic ids) as the original file — the
audit/replay guarantee, test-enforced. This table never holds FHIR resources:
fhirEngine is the sole writer of FHIR storage.

### C-CDA projection → moved to nemsis2ccda

The C-CDA R2.1 projection now lives in its own repo —
[**nemsis2ccda**](https://github.com/FHIRmedicConsulting/nemsis2ccda)
(split 2026-08-07 with full history; separate administration). It consumes
this repo's canonical graph as a dependency: one Layer A, two document
projections. `python -m nemsis2ccda convert <xml> --dem dem.xml`.

### ITI-65 handoff packaging (Phase 5, ADR-008)

`nemsis2fhir.transport.provide_document_bundle(result)` wraps the mPSC document
in an **MHD Provide Document Bundle**: SubmissionSet (`List`) + MHD Minimal
DocumentReference (EntryUUID identifier, type mirrors the Composition,
confidentiality carried as `securityLabel`) + `Binary` (the document,
application/fhir+json) + the Patient. **Validates 0-errors against
`ihe.iti.mhd#4.2.2`** — enforced in the Tier-2 suite. Delivery is pluggable
(`MhdHttpTransport` push, `FileDropTransport` for portable-media/batch; XDR/XDM
can join behind the same `Transport` protocol). CLI:
`python -m nemsis2fhir convert <xml> --iti65`.

### FML fidelity oracle (CI-only Java — ADR-002)

The mapping spec is authored as FML StructureMaps over NEMSIS logical models
(`maps/structuremaps/`, `maps/logical/`) with the ConceptMaps
(`maps/conceptmaps/`) — the upstream-contributable artifact set. Production
execution is **native Python; there is no JVM in the runtime**. In CI, the
reference Java engine inside the same `validator_cli.jar` Tier-2 already uses
executes the authored maps and the harness asserts its output matches the
native mapper on the map-covered surface (native-only enrichments — dual
coding, NV/PN routing, US Core extensions — are the typed-helper layer the
declarative maps intentionally do not cover):

```bash
# fully network-free when the Tier-1 fhirEngine is up (it serves as the
# validator's terminology server); falls back to tx.fhir.org otherwise
NEMSIS2FHIR_TIER1_URL=http://127.0.0.1:8095 ./scripts/fml-oracle.sh
```

There is no mature Python/TypeScript FML engine, and a home-grown one would
check our Python against our Python — the Java reference engine is what makes
the oracle an *oracle*. Panels covered (30 oracle tests, 5 maps × the 6-case
corpus):

- **ePatient** — demographics; sex via cm-nemsis-sex `translate()`.
- **eMedications** — one MedicationAdministration per MedicationGroup, incl.
  the flagship **PN → status=not-done + statusReason** rule and route
  translation via cm-nemsis-medroute (unmatched routes correctly yield no
  standard coding in both engines).
- **eVitals (BP)** — the shared-group-timestamp rule and per-component
  **NV → dual-coded data-absent-reason** via cm-nemsis-nv. The native
  both-components profile fill for source-absent elements is a documented
  native-only enrichment (see `oracle.py`).
- **eProcedures** — SNOMED pass-through / **PN → not-done + statusReason**,
  outcome echo.
- **eSituation** — the principal encounter-diagnosis Condition: **ICD-10-CM**
  pass-through (the XSD-corrected terminology) + symptom onset.

The five semantically riskiest transform families (translate, act-negation,
absence-routing, terminology pass-through ×2) are now oracle-checked. New
panels follow the same pattern: logical model + `.map` + an `oracle.py`
exporter/projection pair.

> **Terminology correction (v3.5.0 XSD is authoritative, applied 2026-08-06):**
> `eSituation.09–.12` (symptoms/impressions) and `eHistory.08` (PMH) are
> **ICD-10-CM**, not SNOMED; `eProcedures.07` complications are NEMSIS-coded
> (3907xxx). `eProcedures.03` SNOMED and `eMedications.03` RxNorm confirmed.
> `docs/01` §3 and the S2T workbook have been corrected to match (cells carry
> a `[corrected 2026-08-06]` audit note).

## Documentation
| File | What it is |
|---|---|
| `docs/01_Architecture_Design.md` | End-to-end system design: components, layered target, terminology/identity/validation, runtime comparison (revised for fhirEngine + Delta OSS), risks. **Read first.** |
| `docs/02_NEMSIS35_to_FHIR_S2T_Mapping.xlsx` | The superset source-to-target mapping — 18 tabs, 212 rows, coverage matrix, terminology/ConceptMap strategy, gap register. The running spec for the mapper. |
| `docs/03_ADRs.md` | 10 architecture decision records (layered output, native-Python-mapper→fhirEngine runtime, terminology, identity/MPI, conformance, validation contract, versioning, transport, fhirEngine-as-SoR, no-Spark). |
| `docs/04_Phased_Roadmap.md` | Phased build plan (P0–P7) with effort/risk and critical path. |
| `CLAUDE.md` | Fast orientation + hard rules for Claude Code sessions. |

## Key design commitments
- **Layered target:** canonical US-Core-aligned resource graph first (durable), mPSC document as a
  thin projection (swappable as the draft IG stabilizes).
- **Runtime:** native Python mapper → fhirEngine REST; **fhirEngine is the FHIR system of record**
  on OSS Delta Lake; StructureMaps/ConceptMaps are the upstream-contributable spec + CI oracle.
- **Complete, upstream-ready superset mapping** — fills the mPSC IG's mostly-empty NEMSIS→FHIR
  table, structured to contribute back to IHE PCC / HL7 EMS WG.

## Related
- [`../fhirEngine`](../fhirEngine) — the FHIR R4 server / repository this loads into.
- IHE EMS-Overall: https://build.fhir.org/ig/IHE/EMS-Overall/
- IHE PCC mPSC: https://build.fhir.org/ig/IHE/PCC.PCS/
- NEMSIS v3.5.0: https://nemsis.org/
