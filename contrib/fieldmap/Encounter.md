# eResponse · eDispatch · eTimes · eScene → Encounter (spine) / Location

Panel tab `Encounter` of the NEMSIS 3.5.0 → FHIR R4 source-to-target workbook (emsInterop). Status column: Mapped = full target defined · Seeded = target assigned · Deferred = intentionally postponed (ledgered, never dropped).

| NEMSIS ID | NEMSIS Element Name | Usage/Card | Repeats | Target FHIR Resource | Target Profile | FHIR Path | Datatype Transform | Terminology / ConceptMap | NV handling | PN handling | mPSC Section | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eResponse.01 | EMS Agency Number | M [1..1] | No | Encounter/Organization | US Core Encounter | Encounter.serviceProvider→Organization | ref | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | Ties Encounter to Organization |
| eResponse.03 | Incident Number | R [1..1] | No | Encounter | US Core Encounter | Encounter.identifier | string→Identifier | system=incident | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eResponse.04 | EMS Response Number | R [1..1] | No | Encounter | US Core Encounter | Encounter.identifier | string→Identifier | system=response | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eResponse.05 | Type of Service Requested | M [1..1] | No | Encounter | US Core Encounter | Encounter.type / serviceType | code | service-type ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eResponse.07 | Unit Transport & Equipment Capability | M [1..1] | No | Encounter | — | Encounter.type (secondary) | code | ConceptMap→SNOMED | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded |  |
| eResponse.08-.12 | Dispatch/Response/Scene/Transport/Turnaround Delay | R [1..*] | Yes | Observation | — | Observation (delay reasons) | code | delay ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded | Operational; may be excluded from CS |
| eResponse.13 | EMS Vehicle (Unit) Number | M [1..1] | No | Encounter/Location | — | Encounter.location.location→Location(vehicle) | string→ref | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eResponse.14 | EMS Unit Call Sign | M [1..1] | No | Location | — | Location.name/alias (vehicle) | string | n/a | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eResponse.16-.18 | Vehicle Dispatch Location / GPS / USNG | O | No | Location | — | Location.position; Location.address | geo→position | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded |  |
| eResponse.19-.22 | Odometer readings (Begin/OnScene/Dest/End) | O | No | Observation | — | Observation (mileage) valueQuantity | decimal→Quantity(mi) | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded | Billing/QA; often excluded from CS |
| eResponse.23 | Response Mode to Scene | M [1..1] | No | Encounter | — | Encounter.priority | code | priority ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | Emergent/non-emergent |
| eResponse.24 | Additional Response Mode Descriptors | R [1..*] | Yes | Encounter | — | Encounter.priority (ext) | code | ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded |  |
| eDispatch.01 | Dispatch Reason | M [1..1] | No | Encounter / Observation | — | Encounter.reasonCode | code | dispatch-reason ConceptMap→SNOMED | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eDispatch.02 | EMD Performed | R [1..1] | No | Observation | — | Observation (EMD performed) valueBoolean/code | code | — | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | EMS Course* | Seeded |  |
| eDispatch.05 | Dispatch Priority (Patient Acuity) | O | No | Encounter | — | Encounter.priority (dispatch) | code | acuity ConceptMap | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded |  |
| eTimes.01 | PSAP Call Date/Time | R [1..1] | No | Encounter/Observation | — | Provenance.occurred / timeline Observation | dateTime | ISO8601+offset | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | Source printed 'EPSAP' (typo) |
| eTimes.03 | Unit Notified by Dispatch Date/Time | M [1..1] | No | Encounter | US Core Encounter | Encounter.period.start (dispatch phase) | dateTime | ISO8601+offset | n/a | n/a | EMS Course* | Mapped |  |
| eTimes.05 | Unit En Route Date/Time | R [1..1] | No | Encounter | — | EncounterHistory / timeline | dateTime |  | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eTimes.06 | Unit Arrived on Scene Date/Time | R [1..1] | No | Encounter | US Core Encounter | Encounter.period.start (on-scene) | dateTime |  | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | Primary Encounter.period.start |
| eTimes.07 | Arrived at Patient Date/Time | R [1..1] | No | Encounter/Observation | — | timeline Observation | dateTime |  | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eTimes.09 | Unit Left Scene Date/Time | R [1..1] | No | Encounter | — | timeline / transport start | dateTime |  | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eTimes.11 | Patient Arrived at Destination Date/Time | R [1..1] | No | Encounter | US Core Encounter | Encounter.period.end (arrival) | dateTime |  | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eTimes.12 | Destination Patient Transfer of Care Date/Time | R [1..1] | No | Encounter | US Core Encounter | Encounter.period.end (transfer) | dateTime |  | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | Handoff moment for mPSC-CS |
| eTimes.02/.04/.08/.10/.13-.17 | Other timeline timestamps | varies | No | Observation/EncounterHistory | — | timeline cluster | dateTime |  | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Seeded | Full timeline in CR; subset in CS |
| eScene.01 | First EMS Unit on Scene | R [1..1] | No | Observation | — | Observation valueBoolean | boolean | — | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | EMS Course* | Seeded |  |
| eScene.06 | Number of Patients at Scene | R [1..1] | No | Observation | — | Observation valueInteger | integer | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eScene.07 | Mass Casualty Incident | R [1..1] | No | Observation / Flag | — | Observation (MCI) valueBoolean; Flag | code | — | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | EMS Course* | Mapped |  |
| eScene.08 | Triage Classification for MCI Patient | R [1..1] | No | Observation | — | Observation.value (triage color) | code | 2708xxx ConceptMap (Red/Yellow/Green/Black) | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | START/SALT triage |
| eScene.09 | Incident Location Type | R [1..1] | No | Location | — | Location.type | code | location-type ConceptMap→v3 RoleCode | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eScene.11 | Scene GPS Location | O | No | Location | — | Location.position (lat/long) | geo→position | n/a | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped |  |
| eScene.15-.23 | Incident Address / City / State / ZIP / County / Country / Census | RE/R | No | Location | — | Location.address | address | — | NV(7701xxx)→data-absent-reason | n/a | EMS Course* | Mapped | Scene location resource |
