# eDisposition → Encounter / Location / Communication

Panel tab `eDisposition` of the NEMSIS 3.5.0 → FHIR R4 source-to-target workbook (emsInterop). Status column: Mapped = full target defined · Seeded = target assigned · Deferred = intentionally postponed (ledgered, never dropped).

| NEMSIS ID | NEMSIS Element Name | Usage/Card | Repeats | Target FHIR Resource | Target Profile | FHIR Path | Datatype Transform | Terminology / ConceptMap | NV handling | PN handling | mPSC Section | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eDisposition.01-.02 | Destination Name / Code | RE [0..1] | No | Location/Organization | — | Encounter.hospitalization.destination→Location | string/code | facility ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.03-.10 | Destination Address/City/State/County/ZIP/Country/GPS/USNG | O/R | No | Location | — | Location.address / position | address/geo | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.11 | Number of Patients Transported in this Unit | RE [0..1] | No | Observation | — | Observation valueInteger | integer | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded |  |
| eDisposition.13-.15 | How Patient Moved to/from Ambulance + Position During Transport | O | Yes | Observation | — | Observation cluster | code | ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded | Src typos: 'deDisposition.15'→eDisposition.15 |
| eDisposition.16 | EMS Transport Method | R [1..1] | No | Encounter | — | Encounter.type (transport) | code | ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.17-.18 | Transport Mode from Scene + Additional Descriptors | R | Yes | Encounter | — | Encounter.priority (transport) | code | emergent/non ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.19 | Final Patient Acuity | R [1..1] | No | Observation | — | Observation (acuity, final) | code | acuity ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.20 | Reason for Choosing Destination | R [1..*] | Yes | Encounter | — | Encounter.hospitalization.reasonCode / ServiceRequest | code | ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.21 | Type of Destination | R [1..1] | No | Location | — | Location.type | code | ConceptMap→v3 RoleCode | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.22 | Hospital In-Patient Destination | R [1..1] | No | Encounter | — | Encounter.hospitalization | code | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded |  |
| eDisposition.23 | Hospital Capability | R [1..*] | Yes | Location/Organization | — | Location.type (capability) | code | trauma/STEMI/stroke center ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | System-of-care routing |
| eDisposition.24 | Destination Team Pre-Arrival Alert or Activation | R [1..1] | No | Communication | — | Communication (prearrival alert) | code | — | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | EMS Course* | Mapped | STEMI/stroke/trauma activation |
| eDisposition.25 | Date/Time of Destination Prearrival Alert | R [1..1] | No | Communication | — | Communication.sent | dateTime | n/a | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.26 | Disposition Instructions Provided | O [0..*] | Yes | Observation/CommunicationRequest | — | Observation / note | code | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded |  |
| eDisposition.27 | Unit Disposition | M [1..1] | No | Encounter | US Core Encounter | Encounter.status / hospitalization | code | 3.5 restructured; ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | Core 'what happened' field |
| eDisposition.28 | Patient Evaluation/Care | R [1..1] | No | Encounter | — | Encounter.status (evaluated/treated) | code | ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.29 | Crew Disposition | R [1..1] | No | Encounter | — | Encounter.status supporting | code | ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDisposition.30 | Transport Disposition | R [1..1] | No | Encounter | US Core Encounter | Encounter.hospitalization.dischargeDisposition | code | transport-disposition ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | Transported/no-transport/refusal |
| eDisposition.31 | Reason for Refusal/Release | O [0..*] | Yes | Encounter/Observation | — | Encounter.reasonCode / Observation | code | ConceptMap | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | EMS Course* | Mapped | AMA/refusal |
| eDisposition.32 | Level of Care Provided per Protocol | R [1..1] | No | Encounter | — | Encounter.type (LOC) | code | ALS/BLS ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
