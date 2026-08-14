# emsInterop

**A poly-HL7 translation engine for NEMSIS-schema'd EMS data.** One NEMSIS v3.5
ePCR goes in; **whichever HL7 format the administrator configures** comes out —
**HL7 v2**, **C-CDA (HL7 v3)**, **FHIR R4**, any combination, or one alone. The
hospital, the state registry, and the HIE each want a different standard, and an
EMS agency should not have to run three integrations to satisfy them — nor emit
formats no one downstream has asked for.

Output is a **deployment setting, not a build**: `mode` takes a single rail or a
list, so the same binary serves an agency whose hospital is on v2 and one whose
HIE is on FHIR.

```json
{ "mode": ["fhir", "adt"] }      // or "ccda", or "fhir", or all three
```

| Rail | Configured as | Output | Who consumes it |
|---|---|---|---|
| **FHIR R4** | `fhir` | US-Core-aligned resource graph + IHE PCC mPSC document, submitted as a transaction Bundle | [fhirEngine](../fhirEngine) or any FHIR server; ITI-65 document sharing |
| **HL7 v2** | `adt` | ADT^A03 (completed call) and ADT^A04 (prearrival), MLLP-delivered | Hospital ADT feeds, encounter-notification networks |
| **C-CDA (v3)** | `ccda` | CCD R2.1, via the [nemsis2CCDA](https://github.com/fhirEMS/nemsis2CCDA) sibling | Hospital document repositories, HIEs on CDA |

### The rails are not equivalent, and are not meant to be

"Poly-HL7" means *the format your consumer speaks*, *not* three interchangeable
copies of the same content. The three containers differ enormously in what they
can hold, so what survives each rail differs too — measured across the corpus:

| Rail | Carries | Never-silently-dropped |
|---|---|---|
| **FHIR R4** | **All 83 national elements** — every one Mapped, Seeded or Deferred, none unaccounted for | **Enforced.** `invariants.check_nothing_dropped` fails the build on a third path |
| **HL7 v2** | ~25 elements across `MSH`/`EVN`/`PID`/`PV1`/`DG1` | Inherent to ADT: an admit/discharge notification has nowhere to put serial vitals or an arrest registry |
| **C-CDA** | 8 of 17 resource types in the graph | **Declared, with named gaps** — see `nemsis2ccda/coverage.py` |

**FHIR is the complete rail.** If you need everything the ePCR said, that is the
one to configure. The other two are projections for consumers who speak those
formats, and they lose content by construction.

The C-CDA rail's known gaps are listed explicitly rather than left to
discovery — most significantly **prior/home medications** (`MedicationStatement`),
which a CCD Medications section could carry and today does not, so a receiving
clinician sees what EMS gave but not what the patient was already taking. Payer,
crew and destination facility are absent for the same reason. A test fails the
build if a resource type reaches that rail with no decision recorded.
| **Inbound** | always available | Hospital discharge (ADT^A03 **or** FHIR Discharge Summary) → matched → NEMSIS `eOutcome` write-back | State registries — closes the outcome loop |

Every rail rides **one canonical mapping** (ADR-001): NEMSIS is mapped once into
a US-Core-aligned FHIR R4 resource graph, and each output is a projection over
that graph. Add a standard by adding a projection, not another mapper — which is
why enabling a second rail cannot change what the first one says.

Supports **NEMSIS 3.5.0 and 3.5.1**, validating against the release each
document declares. No Databricks, no Spark, no JVM in the runtime.

> **Status: v0.3.1 — alpha.** Every roadmap phase (P0–P7) is implemented, and
> the corpus validates clean through the official HL7 validator, a live
> fhirEngine, and the FML fidelity oracle. Five published real-world NEMSIS
> scenario samples convert with **0 validation errors**.
>
> Alpha means: **synthetic data only — not yet run against production PHI**
> (see `docs/05_Operations.md` §1 and `emsinterop preflight`); the target mPSC
> IG is itself a draft (v2.0.0-draft) and moves; the corpora are curated edge
> cases, not a field-scale sample. Read `docs/01_Architecture_Design.md` for
> the design and "Scope & limitations" below before trusting it with real
> patients.

## How it works (short version)

A native **Python mapper** parses the NEMSIS XML, applies ConceptMaps, and builds
one canonical US-Core-aligned FHIR R4 resource graph. Every output standard is a
projection over that single graph — which is what keeps them consistent.

```
                                          ENABLED RAILS ONLY (per `mode`)
                                    ┌─[fhir]─▶ transaction Bundle ─▶ fhirEngine ─▶ Delta ─▶ DuckDB
                                    │            └─▶ mPSC document ─▶ ITI-65 / [PCC-1] handoff
NEMSIS 3.5 XML ─▶ parse ─▶ ConceptMaps ─▶ CANONICAL FHIR R4 GRAPH
   (XSD-gated)                      ├─[adt]──▶ HL7 v2 ADT^A03 / A04 ─▶ MLLP ─▶ hospital ADT feed
                                    └─[ccda]─▶ C-CDA R2.1 CCD ─▶ document repository / HIE

hospital discharge (ADT^A03 | FHIR Discharge Summary) ─▶ match ─▶ NEMSIS eOutcome ─▶ state registry
```

A disabled rail costs nothing — it is never rendered. Within an enabled rail,
endpoints are independently optional: configured, artifacts are delivered;
unconfigured, they are produced and reported, which is how you dry-run a new
partner before pointing at their endpoint.

## Getting started (dev)

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev,bronze,analytics]'
.venv/bin/python -m pytest                       # golden-corpus + unit tests
.venv/bin/python -m emsinterop validate tests/fixtures/pcr_chest_pain.xml
.venv/bin/python -m emsinterop convert tests/fixtures/pcr_chest_pain.xml --issues
.venv/bin/python -m emsinterop convert tests/fixtures/pcr_chest_pain.xml --submit http://localhost:8080
```

Extras: `bronze` (raw-NEMSIS Delta audit/replay), `analytics` (de-id projection),
`dev` (pytest + openpyxl). The core install has no Delta/DuckDB dependency — a
deployment that only converts and transmits needs neither.

### Choosing which standards to emit

Rail selection is configuration, not code. Copy a template, set `mode`, and pass
it with `--config`:

```bash
cp deploy/messaging.example.json my-agency.json     # starter: FHIR + HL7 v2
# edit "mode": "fhir" | "adt" | "ccda", or a list

.venv/bin/python -m emsinterop convert tests/fixtures/pcr_chest_pain.xml \
    --config my-agency.json                          # dispatches the enabled rails
.venv/bin/python -m emsinterop serve --config my-agency.json
```

`convert --config` prints one line per artifact — its rail, whether it was sent,
and any delivery error — so you can see exactly what a config produces before
wiring up endpoints. `deploy/messaging.prod.example.json` is the production
starting point; gate that deploy on `emsinterop preflight --config`.

### The CLI at a glance

| Command | What it does |
|---|---|
| `validate <xml>` | XSD-validate a NEMSIS EMSDataSet; prints an `OperationOutcome` |
| `convert <xml>` | Convert → transaction bundle (or `--document`, `--iti65`, `--adt`, `--config` to dispatch rails, `--submit` to POST) |
| `serve` | At-the-door push endpoint (`POST /push`) running the same pipeline in real time |
| `outcome <discharge> <pcr…>` | Match a hospital ADT^A03 or FHIR Discharge Summary to a PCR; `--apply` writes back eOutcome |
| `land <xml> <table>` | Land raw NEMSIS in the bronze Delta table (audit/replay) |
| `reconcile <bronze> <delta-base>` | Join fhirEngine's dead-letter tables to the conversion issue log → gap register |
| `deid <delta-base> <out>` | Safe-Harbor de-identified analytics projection |
| `package-ig <dir>` | Build the `emsinterop.nemsis` FHIR package (CodeSystem + ValueSets + ConceptMaps) |
| `preflight --config <json>` | Verify a deployment is actually configured for production PHI; exits non-zero until it is |

Layout: `src/emsinterop/` (ingest → model → mapping → terminology → assemble →
submit, plus `outcome/`, `transport/`, `analytics/`, `serve.py`), `maps/` (authored
ConceptMaps, StructureMaps, logical models — the upstream-contributable spec),
`schemas/nemsis/{3.5.0,3.5.1}/` (pinned NEMSIS XSDs), `tests/fixtures/` (XSD-valid golden
corpus), `contrib/` (the IHE contribution package).

### Tier-1 validation (live fhirEngine)

`scripts/tier1-up.sh` boots the sibling fhirEngine (dev profile, synthetic data
only) with US Core 6.1.0 installed and `FHIRENGINE_VALIDATION_PROFILES=declared`,
then the env-gated harness submits the whole corpus and proves idempotent
resubmission:

```bash
./scripts/tier1-up.sh &   # sidecar + server + US Core install
EMSINTEROP_TIER1_URL=http://127.0.0.1:8095 .venv/bin/python -m pytest tests/test_tier1_fhirengine.py -v
```

Submission uses **conditional PUT upserts** (`PUT Type?identifier=urn:emsinterop:resource-id|…`)
because fhirEngine deliberately has no update-as-create; its conditional update
creates on 0 matches (preserving our deterministic client ids, so literal
references hold) and updates in place on 1 match. Agency display names (absent
from the EMSDataSet header) are supplied via `convert(..., agency_names={...})`;
without one the Organization ships `_name` data-absent and withholds its US Core
claim.

### Corpus sweep (generated NEMSIS at volume)

The hand-authored corpus can only prove the mapper handles what we thought of.
[nemsynth](https://github.com/fhirEMS/nemsynth) — a separate public repo,
deliberately with **no dependency on this one** — generates NEMSIS at volume
across 15 clinical presentations, 4 messiness profiles, both releases and
mass-casualty datasets. The sweep converts them and triages what falls out:

```bash
pip install 'git+https://github.com/fhirEMS/nemsynth'
python -m emsinterop.fuzz --count 3000
```

Half the cases are paired with a generated **DEMDataSet** roster, because the
agency name exists only there — without it every `Organization` withholds its
US Core claim and that branch is never swept.

Findings are **deduplicated** by signature (an invariant rule id, or the
exception type plus the innermost frame in this package), so one defect in a
shared path is one finding rather than thousands. Each carries a **byte-
reproducible** replay command. The sweep fails only on signatures absent from
`tests/fuzz-baseline.json`, which is currently empty: a 20,000-case sweep
(~28,000 PatientCareReports, counting MCI) reports **0 findings**.

Coverage is measured, not assumed: `tests/test_corpus_coverage.py` asserts the
generated corpus populates most of the national dataset with **real values**
(93% today). That number is the denominator for the sweep's result — a clean
sweep over a corpus of nils would prove nothing, which is exactly what the
first measurement found (22%).

The rules it applies live in `src/emsinterop/invariants.py` and are shared with
the hostile-fixture tier, so the two cannot drift. `tests/test_invariants.py`
hands each rule input that breaks it — a rule that cannot fail is worse than no
rule, and a clean sweep only means something if the harness can report a defect.

### Tier-2 validation (official HL7 validator — authoritative)

The whole corpus's mPSC document bundles pass the official validator with
**0 errors** against base R4 + US Core 6.1.0 + this repo's authored
StructureDefinitions:

```bash
./scripts/tier2-validate.sh          # java 17+ and ~/Downloads/validator_cli.jar
EMSINTEROP_TIER2=1 .venv/bin/python -m pytest tests/test_tier2_validator.py
```

The document bundle is a **projection**: the reference closure from the
Composition (plus Provenance, targets trimmed to members), deep-copied with all
internal references rewritten to `urn:uuid:` form as FHIR document resolution
requires. Operational resources no section claims (PractitionerRole) stay in
the transaction only. mPSC/IPS profile-level validation is deferred until a
pinnable (non-draft) mPSC package exists.

### Raw-NEMSIS bronze (audit/replay — the mapper's ONE Delta table, ADR-009)

`python -m emsinterop land <xml> <table>` shreds an EMSDataSet into the raw
bronze Delta table (`deltalake`, one row per PCR stored as a self-contained
single-PCR document with its header). Landing is **idempotent by file sha256**;
`ingest.bronze.replay()` returns payloads that XSD-validate and convert to
**byte-identical FHIR** (same deterministic ids) as the original file — the
audit/replay guarantee, test-enforced. This table never holds FHIR resources:
fhirEngine is the sole writer of FHIR storage.

### C-CDA projection → moved to nemsis2ccda

The C-CDA R2.1 projection now lives in its own repo —
[**nemsis2ccda**](https://github.com/fhirEMS/nemsis2CCDA)
(split 2026-08-07 with full history; separate administration). It consumes
this repo's canonical graph as a dependency: one Layer A, two document
projections. `python -m nemsis2ccda convert <xml> --dem dem.xml`.

### ADT^A03 projection (the EMS encounter as the ADT visit)

`python -m emsinterop convert <xml> --adt --dem dem.xml` renders the EMS
call's end-of-visit as an **HL7 v2.5.1 ADT^A03** — the third projection over
Layer A — so EMS encounters reach hospital ADT rails and encounter-notification
networks. PV1-36 uses NUBC discharge-status codes (the vocabulary NEMSIS
eOutcome speaks natively) via `cm-nemsis-nubc-discharge` with clinical
precedence (deceased → 20, refusal/AMA → 07, transported → 02, released → 01);
PV1-44/45 = patient contact → transfer of care; DG1 carries the ICD-10-CM
impressions pass-through (primary F, secondary W); ER7 escaping and deterministic MSH-10 control
ids (pass `message_time` in production). **Sending is policy-driven** (`AdtConfig` /
`--adt [completed|both|prearrival]`): the default sends only the completed
A03 — the common case — while prearrival A04 (A01 structure, EVN at the
destination-team alert time, no discharge fields) is opt-in and self-gates
on the call having a destination, so refusals/no-transports never emit one. Delivery: `MllpTransport` (VT/FS/CR framing, MSA ack codes) joins the
`Transport` protocol alongside MHD HTTP and file drop.

### Inbound outcome loop (Phase 6): hospital discharge → eOutcome write-back

`python -m emsinterop outcome <discharge> <pcr.xml...> [--apply out.xml]`
takes the hospital discharge on either rail — an ADT^A03 (ER7) or a FHIR
Discharge Summary document Bundle (LOINC 18842-5, detected by content); both
reduce to the same transport-neutral `OutcomeRecord`. It then scores each
candidate PCR on three signal groups —
identity (name+DOB or shared identifier), timing (hospital admit within a
window after transfer of care), facility (sender vs EMS destination) — and
links **only when every available signal agrees**; anything partial is
`review` (wrong-patient write-back is the refused failure mode). A linked
discharge writes back the FULL corrected PCR: eOutcome.01/.02 take the NUBC
discharge status verbatim (the vocabulary match with PV1-36), diagnoses land
in .10/.13, the hospital visit number in .03/.04 (Hospital-Receiving), and
the output re-validates against the pinned NEMSIS XSD — the state-registry
resubmission form. Matching thresholds and delta-vs-full submission format
are deliberately conservative defaults, revisable by policy.

### Reverse mapping (Phase 6): FHIR → NEMSIS

The authored ConceptMaps run backwards: `reverse_translate()` reverses only
`equivalent`/`equal` rows (a `wider` row must not reverse — it would
fabricate precision), and `mapping/reverse.py` applies the direction
discipline — the dual-coded NEMSIS original wins when present; reversed
ConceptMaps cover foreign US-Core-only resources. Demographics
(`patient_to_nemsis`) are the round-trip proof, corpus-verified.

### At-the-door push endpoint (Phase 6)

`python -m emsinterop serve --config messaging.json [--bronze table]` — a
stdlib WSGI service: `POST /push` takes a NEMSIS EMSDataSet and runs the
same pipeline as the batch CLI synchronously (XSD → optional bronze landing
→ convert → per-rail dispatch), so with fhirEngine in `single` mode the
encounter is queryable the moment the push returns; prearrival A04 rides
the same AdtConfig policy. 422 + OperationOutcome for invalid XML, 502 when
a configured rail fails, delivery summaries only (never artifacts) in the
response. Deploy behind TLS + an authenticating proxy.

### ITI-65 handoff packaging (Phase 5, ADR-008)

`emsinterop.transport.provide_document_bundle(result)` wraps the mPSC document
in an **MHD Provide Document Bundle**: SubmissionSet (`List`) + MHD Minimal
DocumentReference (EntryUUID identifier, type mirrors the Composition,
confidentiality carried as `securityLabel`) + `Binary` (the document,
application/fhir+json) + the Patient. **Validates 0-errors against
`ihe.iti.mhd#4.2.2`** — enforced in the Tier-2 suite. Delivery is pluggable
(`MhdHttpTransport` push, `FileDropTransport` for portable-media/batch; XDR/XDM
can join behind the same `Transport` protocol). CLI:
`python -m emsinterop convert <xml> --iti65`.

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
EMSINTEROP_TIER1_URL=http://127.0.0.1:8095 ./scripts/fml-oracle.sh
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

## Deployment messaging configuration

One JSON config picks the rails (`python -m emsinterop convert <xml> --config messaging.json`):
`mode` is a rail or list of rails from `fhir | adt | ccda` (legacy shorthands
`both` = fhir+adt, `all`) — FHIR (transaction to fhirEngine + optional ITI-65)
is the default; ADT rides the `AdtConfig` policy (completed-call A03 by
default, prearrival opt-in); `ccda` renders a C-CDA R2.1 CCD via the optional
[nemsis2ccda](https://github.com/fhirEMS/nemsis2CCDA) package
(install it to enable the rail; `ccda.out_dir` writes the documents).
Endpoints are optional per rail (fhirEngine URL, MHD recipient, MLLP
host:port) — configured, artifacts are delivered; unconfigured, they're
produced and reported. See `emsinterop/config.py`.

## Scope & limitations (read before production use)

What the alpha label means concretely:

- **Synthetic data only.** Nothing here has processed production PHI. Before it does,
  fhirEngine must boot under `FHIRENGINE_SECURITY_PROFILE=production` (fail-closed on
  auth/audit/TLS) and the DS4P/consent posture in `docs/05_Operations.md` §1 must be
  reviewed by someone accountable for it.
- **The target IG is a moving draft.** IHE PCC mPSC is at v2.0.0-draft with no tagged
  release; its published and master branches differ. Layer B (document assembly) is
  deliberately thin so the canonical graph survives IG churn — but mPSC conformance
  claims are provisional until the IG stabilizes. Findings we filed against it are in
  `contrib/gap-report.md`.
- **Three corpora, none of them field-scale.** The *golden* corpus (six cases:
  cardiac arrest, MCI, interfacility, pediatric, refusal, chest pain) covers
  NV/PN, negation, and repeating groups. The *hostile* corpus
  (`tests/fixtures/hostile/`) is XSD-valid input that broke us once — a palpated
  BP, an off-scale glucose, a comment inside a value, a refused sex, a PCR
  number with a slash — and runs in default CI. The *discovery* tier
  (`EMSINTEROP_SAMPLES`) runs real published NEMSIS scenario samples; when it
  finds something new, that gets distilled into a hostile fixture. Real agency
  exports will still surface elements none of these exercise; the conversion
  issue log is designed to make that visible rather than silent.
- **Known non-conformance**, a standards limitation rather than a mapping bug:
  - *`24:00:00±hh:mm` is XSD-valid NEMSIS and invalid FHIR.* Not yet normalized.
- **Absence is carried, never papered over.** A VitalGroup with no `eVitals.01`
  is expressed at the encounter's **date** precision — FHIR `dateTime` is
  variable-precision, so this asserts exactly what the source supports and no
  time of day it never recorded. An unrecorded **sex** maps to
  `administrative-gender#unknown` via `cm-nemsis-sex` — FHIR's own "the gender
  is not known", which is the receiver's situation whether the field was
  refused, not recorded, or not applicable. Those rows are `equivalence=wider`,
  so the reverse mapper can never resurrect "Refused" from `unknown`. Where
  nothing is derivable at all, the primitive carries the **standard**
  `data-absent-reason` extension (no bespoke extension — a custom one would
  force every downstream consumer to load our StructureDefinition first). Coded
  elements still dual-code the NEMSIS original natively in their
  CodeableConcept; on a primitive the exact source code lives in the conversion
  issue ledger.
- **Deferred by design:** the `eOutcome` panel beyond the implemented loop, `ePayment`
  billing detail, and reverse mapping outside demographics. All are ledgered as
  `Deferred` in the workbook, never silently dropped.
- **Single-node throughput.** No Spark/cluster path (ADR-010). Fine for agency-scale
  PCR volumes; a very large state-registry backfill would need revisiting.
- **NEMSIS 3.5.0** is the pinned source version; 3.5.1 deltas are handled as overrides
  but not corpus-tested.

## Documentation
| File | What it is |
|---|---|
| `docs/01_Architecture_Design.md` | End-to-end system design: components, layered target, terminology/identity/validation, runtime comparison (revised for fhirEngine + Delta OSS), risks. **Read first.** |
| `docs/02_NEMSIS35_to_FHIR_S2T_Mapping.xlsx` | The superset source-to-target mapping — 18 tabs, 212 rows, coverage matrix, terminology/ConceptMap strategy, gap register. The running spec for the mapper. |
| `docs/03_ADRs.md` | 10 architecture decision records (layered output, native-Python-mapper→fhirEngine runtime, terminology, identity/MPI, conformance, validation contract, versioning, transport, fhirEngine-as-SoR, no-Spark). |
| `docs/04_Phased_Roadmap.md` | Phased build plan (P0–P7) with effort/risk and critical path. |
| `docs/05_Operations.md` | Deployment runbook: prod gates, terminology provisioning, land→convert→dispatch→reconcile pipeline, promotion, de-id analytics, releases. |
| `docs/06_Synthetic_Corpus_Plan.md` | Plan for `nemsynth`, a Synthea-equivalent synthetic NEMSIS generator — the path to corpus breadth while real agency exports are unavailable. |
| `contrib/` | The IHE PCC mPSC contribution package (Phase 7): completed field map export, verified gap report, six channel-neutral proposal documents (no repo issues are opened; delivery channel is Chad's call). |
| `CLAUDE.md` | Fast orientation + hard rules for Claude Code sessions. |

## Key design commitments
- **Layered target:** canonical US-Core-aligned resource graph first (durable), mPSC document as a
  thin projection (swappable as the draft IG stabilizes).
- **Runtime:** native Python mapper → fhirEngine REST; **fhirEngine is the FHIR system of record**
  on OSS Delta Lake; StructureMaps/ConceptMaps are the upstream-contributable spec + CI oracle.
- **Complete, upstream-ready superset mapping** — fills the mPSC IG's mostly-empty NEMSIS→FHIR
  table, structured to contribute back to IHE PCC / HL7 EMS WG.

## Related
- **This repo:** <https://github.com/fhirEMS/emsinterop> — releases carry the
  `emsinterop.nemsis` terminology package as a tarball.
- [`../fhirEngine`](../fhirEngine) — the FHIR R4 server / repository this loads into.
- IHE EMS-Overall: https://build.fhir.org/ig/IHE/EMS-Overall/
- IHE PCC mPSC: https://build.fhir.org/ig/IHE/PCC.PCS/
- NEMSIS v3.5.0: https://nemsis.org/
