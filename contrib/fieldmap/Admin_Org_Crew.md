# eRecord · dAgency · dPersonnel · eCrew · eCustom → Composition / Organization / Practitioner / Provenance

Panel tab `Admin_Org_Crew` of the NEMSIS 3.5.0 → FHIR R4 source-to-target workbook (emsInterop). Status column: Mapped = full target defined · Seeded = target assigned · Deferred = intentionally postponed (ledgered, never dropped).

| NEMSIS ID | NEMSIS Element Name | Usage/Card | Repeats | Target FHIR Resource | Target Profile | FHIR Path | Datatype Transform | Terminology / ConceptMap | NV handling | PN handling | mPSC Section | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eRecord.01 | Patient Care Report Number | M [1..1] | No | Composition / Bundle | IHE.PCC.FHIR.MS.Composition | Composition.identifier; Bundle.identifier | string→Identifier | system=urn:nemsis:pcr | n/a | n/a | (header) | Mapped | PCR business key; also Provenance target |
| eRecord.02 | Software Creator | M [1..1] | No | Device / Provenance | — | Device.manufacturer; Provenance.entity | string | — | n/a | n/a | (header) | Seeded | Source-software attribution |
| eRecord.03 | Software Name | M [1..1] | No | Device | — | Device.deviceName.name | string | — | n/a | n/a | (header) | Seeded |  |
| eRecord.04 | Software Version | M [1..1] | No | Device | — | Device.version.value | string | — | n/a | n/a | (header) | Seeded |  |
| dAgency.01 | EMS Agency Unique State ID | M [1..1] | No | Organization | US Core Organization | Organization.identifier | string→Identifier | system=state agency id | n/a | n/a | (author) | Mapped | IG-ANCHORED mapping (only populated cells in mPSC) |
| dAgency.02 | EMS Agency Number | M [1..1] | No | Organization | US Core Organization | Organization.identifier | string→Identifier | system=NASEMSO/national | n/a | n/a | (author) | Mapped | IG-ANCHORED |
| dAgency.03 | EMS Agency Name | RE [0..1] | No | Organization | US Core Organization | Organization.name | string | n/a | NV(7701xxx)→data-absent-reason | n/a | (author) | Mapped | IG-ANCHORED |
| dAgency.04 | EMS Agency State | M [1..1] | No | Organization | US Core Organization | Organization.address.state | string→address | USPS state | n/a | n/a | (author) | Mapped | IG-ANCHORED |
| dAgency.25 | National Provider Identifier (NPI) | O | No | Organization | US Core Organization | Organization.identifier (NPI) | string→Identifier | system=http://hl7.org/fhir/sid/us-npi | NV(7701xxx)→data-absent-reason | n/a | (author) | Mapped |  |
| dPersonnel.* | Personnel roster / certifications | varies | Yes | Practitioner + PractitionerRole | US Core Practitioner/Role | Practitioner.identifier/name; PractitionerRole.code | group→resource | cert level ConceptMap | NV(7701xxx)→data-absent-reason | n/a | (author) | Seeded | Referenced by eMedications.09/eProcedures.09 crew IDs |
| eCrew.01 | Crew Member ID | RE [0..1] | Yes | PractitionerRole | US Core PractitionerRole | PractitionerRole.practitioner→dPersonnel | string→ref | links to dPersonnel | NV(7701xxx)→data-absent-reason | n/a | (author) | Mapped |  |
| eCrew.02 | Crew Member Level | RE [0..1] | Yes | PractitionerRole | US Core PractitionerRole | PractitionerRole.code | code | cert-level ConceptMap | NV(7701xxx)→data-absent-reason | n/a | (author) | Mapped |  |
| eCrew.03 | Crew Member Response Role | RE [0..*] | Yes | PractitionerRole | US Core PractitionerRole | PractitionerRole.specialty/code | code | response-role ConceptMap | NV(7701xxx)→data-absent-reason | n/a | (author) | Mapped |  |
| eCustomConfiguration.01-.09 | Custom element definitions | varies | Yes | Observation (definition) | — | Observation / Observation.value[x] / dataAbsentReason | per IG | local | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | (author) | Mapped | IG-ANCHORED to Observation; .07 NV→valueCodeableConcept, .08 PN→dataAbsentReason, .09 grouping→identifier |
| eCustomResults.01-.03 | Custom element results | varies | Yes | Observation | — | Observation.value[x]; CorrelationID→derivedFrom | per IG | local | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | Results | Mapped | CorrelationID links result↔config (.02 ref, .03 correlation) |
