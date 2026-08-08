# Operations runbook — running emsInterop against fhirEngine

Roadmap P5's "governed and observable" deliverable, written down. This is the
deployment-facing companion to `01_Architecture_Design.md` §7–§8; everything
here exists in code today.

## 1. Gates before any PHI

**fhirEngine side** — boot with `FHIRENGINE_SECURITY_PROFILE=production`
(`deploy/docker-compose.prod.yml` in the fhirEngine repo sets it). The
profile is fail-closed: the server refuses to start until auth
(`FHIRENGINE_AUTH_ENABLED`), audit (`FHIRENGINE_AUDIT_ENABLED`), transport
security (`FHIRENGINE_TLS_CERT`/`KEY` or `FHIRENGINE_TLS_TERMINATED_AT_PROXY`),
and persistent OAuth signing keys are configured. Consent/DS4P read-time
enforcement (`FHIRENGINE_CONSENT_ENFORCEMENT`) is advisory even in
production — turn it on when serving 42 CFR Part 2 data; the mapper's labels
(below) are what it consumes.

**Mapper side** — the mapper tags, fhirEngine enforces: DS4P labels are
applied at creation (substance-use `eHistory.17` → `R` + `ETH`, rolled up to
`Composition.confidentiality` and the ITI-65 `DocumentReference.securityLabel`)
and verified end-to-end by the Tier-1 harness (`test_ds4p_labels_survive_round_trip`).
Mapper logging is PHI-safe by construction (`emsinterop.log`): the `event()`
helper only emits allowlisted metadata fields (ids, codes, counts); the
library root logger has a `NullHandler` — attach handlers in the embedding
service to collect events, and nothing you attach can receive a patient value.

## 2. Terminology provisioning

fhirEngine must know the NEMSIS codes the mapper dual-codes, or declared-profile
validation would flag them:

```sh
python -m emsinterop package-ig /tmp/nemsis-pkg
cd ../fhirEngine/packages/server
npx tsx scripts/fhirengine-terminology.ts install-ig /tmp/nemsis-pkg emsinterop.nemsis
```

`scripts/tier1-up.sh` does both automatically for the dev stack (alongside
US Core 6.1.0). Tagged releases attach the same package as
`emsinterop.nemsis-<version>.tgz` (`.github/workflows/release.yml`); unpack and
`install-ig` it on upgrade. Idempotent — re-install after every ruleset release.

## 3. The steady-state pipeline

```
land → convert → dispatch (fhir | adt | ccda per MessagingConfig) → reconcile
```

- `python -m emsinterop land <xml> <bronze-table>` — raw-NEMSIS bronze, the
  mapper's one Delta table (hash-idempotent; safe to re-sweep a directory).
- `python -m emsinterop convert <xml> --config deploy.json --issues-out issues.jsonl`
  — converts and delivers per the deployment's messaging config, appending
  the conversion issue log (including any submit-time rejection: fhirEngine
  rejects transactions atomically, so the returned OperationOutcome is folded
  into the log — it will never appear in the server-side dead-letter).
  Non-zero exit when any rail failed.
- **Reconcile (nightly):**
  `python -m emsinterop reconcile <bronze-table> <FHIRENGINE_DELTA_BASE> --out gap-register.json`
  — replays bronze, re-converts, and joins fhirEngine's `deadletter/<type>`
  Delta tables (read-only) back to PCRs by deterministic resource id / PCR
  identifier. The output is the gap-register feed for the S2T workbook; a
  non-empty `unmatched_dead_letter` means some *other* client's submissions
  are failing, not ours.

## 3b. Real-time push (at-the-door)

`python -m emsinterop serve --config deploy.json --bronze <bronze-table>`
runs the push endpoint (default `127.0.0.1:8096`). EMS units (or the CAD/ePCR
bridge) `POST /push` the EMSDataSet as the crew departs scene; the same
config rails fire immediately — enable `adt.send_prearrival` for the A04.
The endpoint is mechanism only: put TLS and authentication in front of it
(same proxy posture as fhirEngine), and point it at the bronze table so
pushed calls are audit-landed before conversion. `GET /healthz` for probes.

## 4. Medallion promotion (fhirEngine `medallion` mode only)

Default `single` mode needs none of this (read-after-write off Bronze). In
`medallion` mode, promotion is fhirEngine's CLI — `npm run promote` (full) or
`npm run promote -- --incremental` (CDF watermark) — run as a periodic loop
under systemd/cron/container restart. fhirEngine's ADR-0026 explicitly
rejected Dagster/Airflow for v1; the roadmap's "fhirengine-promote/Dagster"
option resolved to the CLI loop. Patient promotes first (MPI survivor map);
schedule promotion more frequently than the reconcile sweep so Gold is fresh
when analytics read it.

## 5. De-identified analytics

```sh
python -m emsinterop deid <FHIRENGINE_DELTA_BASE> /srv/analytics/deid --salt "$DEID_SALT"
```

Materializes Safe-Harbor `encounters` + `vitals` Delta tables (allowlist
projection: salted pseudonyms, year-only dates, age capped at 90, state+ZIP3
with restricted prefixes nulled). Reads `gold/<type>` (falls back to
`bronze/<type>` in single mode), overwrites its outputs — re-run on a schedule
after promotion. Keep `DEID_SALT` in the deployment's secret store: a stable
salt gives cross-run linkage; omitting it gives a fresh salt (linkage within
one run only). DuckDB (or anything that reads Delta) queries the outputs;
the identified store is never exposed to analytics.

## 6. Release process

**Gates, in order.** The first two run in CI on every push; the last two are
local because they need a live server / JVM + network.

```sh
python -m pytest                                          # 1. local suite
EMSINTEROP_TIER2=1 EMSINTEROP_VALIDATOR_JAR=~/validator_cli.jar \
  python -m pytest tests/test_tier2_validator.py          # 2. official HL7 validator (authoritative)
./scripts/tier1-up.sh &                                   # 3. live fhirEngine (~18 min harness)
EMSINTEROP_TIER1_URL=http://127.0.0.1:8095 \
  python -m pytest tests/test_tier1_fhirengine.py
EMSINTEROP_FML_ORACLE=1 python -m pytest tests/test_fml_oracle.py   # 4. FML fidelity oracle
```

**Cut the release.** Bump `version` in `pyproject.toml` and add the matching
`## vX.Y.Z` section to `CHANGELOG.md` (the workflow reads that section verbatim
as the release notes and **fails if it is missing**). Then tag and push:

```sh
git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin main --follow-tags
```

The workflow builds the `emsinterop.nemsis` terminology package, refuses a
version/tag mismatch, attaches the tarball, and marks any `0.x` or
suffixed (`a1`/`rc1`) tag as a GitHub pre-release.

**Downstream.** `nemsis2ccda` pins `emsinterop>=X.Y,<X.Y+1`; a minor bump means
bumping that cap in the sibling repo and re-running its suite. The compatibility
surface it consumes is `MappingContext` (`resources`, `pcr`, `header`, `rid()`,
`agency_names`), `convert()`/`ConversionResult`, and the corpus layout — changes
there need a heads-up, not just a version bump.
