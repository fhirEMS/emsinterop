# ePayment → Coverage / Contract

Panel tab `ePayment` of the NEMSIS 3.5.0 → FHIR R4 source-to-target workbook (emsInterop). Status column: Mapped = full target defined · Seeded = target assigned · Deferred = intentionally postponed (ledgered, never dropped).

| NEMSIS ID | NEMSIS Element Name | Usage/Card | Repeats | Target FHIR Resource | Target Profile | FHIR Path | Datatype Transform | Terminology / ConceptMap | NV handling | PN handling | mPSC Section | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ePayment.01 | Primary Method of Payment | R [1..1] | No | Coverage | US Core Coverage | Coverage.type | code | payment-type ConceptMap | NV(7701xxx)→data-absent-reason | n/a | Payers | Mapped | Feeds optional Payers section (48768-6) |
| ePayment.02-.07 | Physician Certification Statement (PCS) fields | O | No | Contract / DocumentReference | — | Contract (PCS) | mixed | — | NV(7701xxx)→data-absent-reason | n/a | Payers | Deferred | Billing detail; CR/attachment |
| ePayment.09-.16 | Insurance Company ID/Name/Priority/Address | O | Yes | Coverage/Organization | US Core Coverage | Coverage.payor→Organization | mixed | — | NV(7701xxx)→data-absent-reason | n/a | Payers | Seeded |  |
| ePayment.17-.22 | Group ID / Policy ID / Insured name / Relationship | O | No | Coverage | US Core Coverage | Coverage.subscriberId; Coverage.relationship | mixed | relationship ConceptMap | NV(7701xxx)→data-absent-reason | n/a | Payers | Seeded |  |
| ePayment.23-.39 | Closest Relative/Guardian + Employer details | O | No | RelatedPerson | — | RelatedPerson / Patient.contact | mixed | — | NV(7701xxx)→data-absent-reason | n/a | (subject) | Deferred | Contact/billing; CR only |
| ePayment.40-.57 | CMS service level / condition codes / transport indicators / supply items | O/R | Yes | Coverage/Claim | — | Coverage.class / Claim | mixed | CMS ConceptMaps | NV(7701xxx)→data-absent-reason | n/a | Payers | Deferred | Billing/claims; out of clinical scope |
| ePayment.50 | CMS Service Level | R [1..1] | No | Coverage/Encounter | — | Encounter.type (CMS LOS) | code | CMS ConceptMap | NV(7701xxx)→data-absent-reason | n/a | Payers | Seeded |  |
| ePayment.58-.60 | Insurance Group Name / Company Phone / Insured DOB | O | No | Coverage | US Core Coverage | Coverage.class; payor.telecom | mixed | — | NV(7701xxx)→data-absent-reason | n/a | Payers | Deferred | Out-of-order in source (mid-panel) |
