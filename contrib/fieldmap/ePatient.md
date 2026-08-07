# ePatient → Patient (US Core / IHE PCC Patient)

Panel tab `ePatient` of the NEMSIS 3.5.0 → FHIR R4 source-to-target workbook (emsInterop). Status column: Mapped = full target defined · Seeded = target assigned · Deferred = intentionally postponed (ledgered, never dropped).

| NEMSIS ID | NEMSIS Element Name | Usage/Card | Repeats | Target FHIR Resource | Target Profile | FHIR Path | Datatype Transform | Terminology / ConceptMap | NV handling | PN handling | mPSC Section | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ePatient.01 | EMS Patient ID | O [0..1] | No | Patient | IHE.PCC.Patient / US Core Patient | Patient.identifier | string→Identifier | system=agency patient id | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped |  |
| ePatient.02 | Last Name | RE [0..1] | No | Patient | US Core Patient | Patient.name.family | string | n/a | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped | May be unknown at scene |
| ePatient.03 | First Name | RE [0..1] | No | Patient | US Core Patient | Patient.name.given | string | n/a | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped |  |
| ePatient.04 | Middle Initial/Name | O | No | Patient | US Core Patient | Patient.name.given[1] | string | n/a | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped |  |
| ePatient.05-.11 | Home Address/City/County/State/ZIP/Country/Census | O/R | No | Patient | US Core Patient | Patient.address | address | USPS/FIPS | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped |  |
| ePatient.12 | Social Security Number | O | No | Patient | US Core Patient | Patient.identifier (SSN) | string→Identifier | system=us-ssn | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped | PHI — governance-gated |
| ePatient.13 | Gender (DEPRECATED in 3.5.0) | R [1..1] | No | Patient | US Core Patient | Patient.gender | code | admin-gender ConceptMap | NV(7701xxx)→data-absent-reason | n/a | (subject) | Deferred | LEGACY fallback only — prefer .25 (ADR-007) |
| ePatient.25 | Sex (replaces .13) | R | No | Patient | US Core Patient | Patient.gender + US Core Sex/birthsex ext | code | admin-gender / birthsex ConceptMap | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped | SOURCE OF TRUTH for sex (ADR-007) |
| ePatient.14 | Race | R [1..*] | Yes | Patient | US Core Patient | Patient.extension (us-core-race) + pcc-uv-race | code | OMB race → CDC Race&Ethnicity ConceptMap | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped | Dual-carry US Core + mPSC ext (ADR-006) |
| ePatient.15 | Age | R [1..1] | No | Patient/Observation | US Core Patient | Patient.birthDate (derive) / Observation age | integer | with .16 units | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped | When DOB absent, keep age Observation |
| ePatient.16 | Age Units | R [1..1] | No | (qualifier) | — | (units for .15) | code | age-unit ConceptMap→UCUM | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped | Neonatal: days/hours |
| ePatient.17 | Date of Birth | RE [0..1] | No | Patient | US Core Patient | Patient.birthDate | date | n/a | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped |  |
| ePatient.18 | Patient's Phone Number | O [0..*] | Yes | Patient | US Core Patient | Patient.telecom (phone) | contactPoint | n/a | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped |  |
| ePatient.19 | Patient's Email Address | O [0..*] | Yes | Patient | US Core Patient | Patient.telecom (email) | contactPoint | n/a | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped |  |
| ePatient.20-.21 | Driver's License State / Number | O | No | Patient | US Core Patient | Patient.identifier (DL) | string→Identifier | system=state DMV | NV(7701xxx)→data-absent-reason | n/a | (subject) | Mapped |  |
| ePatient.22 | Alternate Home Residence | RE [0..1] | No | Patient | — | Patient.extension (residence type) | code | residence ConceptMap | NV(7701xxx)→data-absent-reason | n/a | (subject) | Seeded | Homeless/SNF/etc. |
