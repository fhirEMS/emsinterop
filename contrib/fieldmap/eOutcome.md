# eOutcome → (external QORE) — deferred / outcome loop

Panel tab `eOutcome` of the NEMSIS 3.5.0 → FHIR R4 source-to-target workbook (emsInterop). Status column: Mapped = full target defined · Seeded = target assigned · Deferred = intentionally postponed (ledgered, never dropped).

| NEMSIS ID | NEMSIS Element Name | Usage/Card | Repeats | Target FHIR Resource | Target Profile | FHIR Path | Datatype Transform | Terminology / ConceptMap | NV handling | PN handling | mPSC Section | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eOutcome.01 | Emergency Department Disposition | R [1..1] | No | (external) QORE / Observation | QRPH QORE | → QORE profile | code | N/A in mPSC | NV(7701xxx)→data-absent-reason | n/a | (outcome) | Deferred | IG punts to external QORE; future outcome-loop input |
| eOutcome.02 | Hospital Disposition | R [1..1] | No | (external) QORE / Observation | QRPH QORE | → QORE profile | code | N/A | NV(7701xxx)→data-absent-reason | n/a | (outcome) | Deferred | Outcome loop (Phase 6) |
| eOutcome.03-.05 | External Report ID/Type + Registry Type | O | No | Observation/DocumentReference | — | Observation.identifier / DocumentReference | string | — | NV(7701xxx)→data-absent-reason | n/a | (outcome) | Deferred |  |
| eOutcome.09-.13 | ED/Hospital Procedures + Diagnoses | R | Yes | Procedure/Condition | — | Procedure / Condition (hospital) | code | SNOMED/ICD-10 | NV(7701xxx)→data-absent-reason | n/a | (outcome) | Deferred | Populated post-discharge, not by EMS |
| eOutcome.11/.16/.18-.20 | Hospital admit/discharge/ED admit + procedure timestamps | R | No | Encounter/Procedure | — | Encounter.period / Procedure.performed | dateTime | n/a | NV(7701xxx)→data-absent-reason | n/a | (outcome) | Deferred | Write-back target for outcome loop |
