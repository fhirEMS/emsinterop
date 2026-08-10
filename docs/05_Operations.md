# Operations runbook — running emsInterop against fhirEngine

Roadmap P5's "governed and observable" deliverable, written down. This is the
deployment-facing companion to `01_Architecture_Design.md` §7–§8; everything
here exists in code today.

## 1. Enabling production PHI

Until this procedure passes, the deployment runs **synthetic data only**. That
is the default and it is deliberate: reaching real patient data should require
a decision, not the absence of one.

### 1.1 Run the preflight — it is the machine-checkable gate

```sh
EMSINTEROP_ALLOW_PHI=1 python -m emsinterop preflight --config deploy.json
```

Exits non-zero until every required control is actually in place, and prints
what to fix. Wire it into the deploy pipeline ahead of the first real
submission; a template config is in `deploy/messaging.prod.example.json`.

What it verifies, from outside the system:

| Check | Why it is required |
|---|---|
| `EMSINTEROP_ALLOW_PHI=1` | Explicit opt-in. Its absence is the safe default. |
| Endpoints use TLS (`https://`) | PHI in cleartext is a transmission-security failure, HIPAA §164.312(e). |
| fhirEngine **rejects unauthenticated reads** | Proves auth is on from the outside, rather than trusting configuration. An anonymous `Patient` search that succeeds is a hard fail. |
| Submission credential configured | A server enforcing auth rejects every submission without one. |
| NEMSIS terminology installed | Otherwise every dual-coded NEMSIS code fails validation under declared-profile enforcement. |
| MLLP channel (warning) | MLLP has no transport security of its own; the preflight cannot see your tunnel, so a human confirms it. |

### 1.2 fhirEngine must boot fail-closed

Set `FHIRENGINE_SECURITY_PROFILE=production` (`deploy/docker-compose.prod.yml`
in the fhirEngine repo). The server then **refuses to start** until auth
(`FHIRENGINE_AUTH_ENABLED`), audit (`FHIRENGINE_AUDIT_ENABLED`), transport
security (`FHIRENGINE_TLS_CERT`/`KEY`, or `FHIRENGINE_TLS_TERMINATED_AT_PROXY`
when a proxy terminates it), and persistent OAuth signing keys are configured.

Consent/DS4P read-time enforcement (`FHIRENGINE_CONSENT_ENFORCEMENT`) is
advisory *even in production* — turn it on before serving 42 CFR Part 2 data.
The mapper's labels are what it consumes.

### 1.3 What the mapper already guarantees

- **DS4P labels** are applied at creation (substance-use `eHistory.17` → `R` +
  `ETH`, rolled up to `Composition.confidentiality` and the ITI-65
  `DocumentReference.securityLabel`) and verified end-to-end by Tier-1
  (`test_ds4p_labels_survive_round_trip`).
- **PHI-safe logging** is structural, not a convention: `emsinterop.log.event()`
  drops any field outside its metadata allowlist, so no handler you attach can
  receive a patient value. The library root logger carries a `NullHandler` —
  attach your own to collect events.
- **The push endpoint** rejects doctypes (XXE/entity expansion), caps request
  bodies, and quarantines malformed input as a 422 rather than a traceback.
  Deploy it behind TLS and an authenticating proxy regardless.

### 1.4 What no script can check — the actual gate

The preflight verifies configuration. It does **not** certify compliance, and
its output says so. Before real patient data flows, someone accountable must
confirm:

- a **BAA** is in place with every party touching the data (hosting, the
  receiving facility, any HIE);
- a **risk assessment / security review** has been done for this deployment;
- the **consent and DS4P policy** matches the jurisdiction and the data —
  42 CFR Part 2 substance-use records carry restrictions beyond HIPAA;
- **retention, breach-notification, and audit-review** procedures exist and
  someone owns them;
- **incident rollback** is understood: the raw-NEMSIS bronze table and
  fhirEngine's `_history` are both PHI once real data lands, and the de-id
  projection's salt becomes a re-identification key that needs protecting.

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
