# eArrest → Observation / Procedure

Panel tab `eArrest` of the NEMSIS 3.5.0 → FHIR R4 source-to-target workbook (emsInterop). Status column: Mapped = full target defined · Seeded = target assigned · Deferred = intentionally postponed (ledgered, never dropped).

| NEMSIS ID | NEMSIS Element Name | Usage/Card | Repeats | Target FHIR Resource | Target Profile | FHIR Path | Datatype Transform | Terminology / ConceptMap | NV handling | PN handling | mPSC Section | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eArrest.01 | Cardiac Arrest | R [1..1] | No | Observation | — | Observation (cardiac arrest) valueCodeableConcept | code | yes/no/prior ConceptMap | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | Problems | Mapped | GATE field; PN=present-prior-to-EMS |
| eArrest.02 | Cardiac Arrest Etiology | R [1..1] | No | Observation/Condition | — | Condition.code / Observation | code | SNOMED | NV(7701xxx)→data-absent-reason | n/a | Problems | Mapped |  |
| eArrest.03 | Resuscitation Attempted By EMS | R [1..*] | Yes | Procedure | — | Procedure (resuscitation) | code | SNOMED | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | Procedures* | Mapped |  |
| eArrest.04 | Arrest Witnessed By | R [1..*] | Yes | Observation | — | Observation valueCodeableConcept | code | ConceptMap | NV(7701xxx)→data-absent-reason | n/a | Problems | Mapped |  |
| eArrest.07 | AED Use Prior to EMS Arrival | R [1..1] | No | Procedure/Observation | — | Procedure (AED, performer=other) | code | — | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | Procedures* | Mapped | Bystander/first responder |
| eArrest.09 | Type of CPR Provided | R [1..*] | Yes | Procedure | — | Procedure (CPR).code | code | SNOMED | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | Procedures* | Mapped |  |
| eArrest.10 | Therapeutic Hypothermia by EMS | O | No | Procedure | — | Procedure (hypothermia) | code | SNOMED | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | Procedures* | Seeded |  |
| eArrest.11 | First Monitored Arrest Rhythm | R [1..1] | No | Observation | — | Observation (rhythm) valueCodeableConcept | code | rhythm ConceptMap (Asystole/VF/etc.) | NV(7701xxx)→data-absent-reason | n/a | Vitals* | Mapped |  |
| eArrest.12 | Any Return of Spontaneous Circulation | R [1..*] | Yes | Observation | — | Observation (ROSC) | code | — | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | Problems | Mapped |  |
| eArrest.14 | Date/Time of Cardiac Arrest | R [1..1] | No | Observation | — | Observation.effectiveDateTime | dateTime | n/a | NV(7701xxx)→data-absent-reason | n/a | Problems | Mapped |  |
| eArrest.15 | Date/Time Resuscitation Discontinued | RE [0..1] | No | Procedure | — | Procedure.performedPeriod.end | dateTime | n/a | NV(7701xxx)→data-absent-reason | n/a | Procedures* | Mapped |  |
| eArrest.16 | Reason CPR/Resuscitation Discontinued | R [1..1] | No | Procedure | — | Procedure.statusReason / outcome | code | ConceptMap | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | Procedures* | Mapped |  |
| eArrest.17 | Cardiac Rhythm on Arrival at Destination | R [1..*] | Yes | Observation | — | Observation (rhythm at dest) | code | rhythm ConceptMap | NV(7701xxx)→data-absent-reason | n/a | Vitals* | Mapped |  |
| eArrest.18 | End of EMS Cardiac Arrest Event | R [1..1] | No | Observation | — | Observation valueCodeableConcept | code | ConceptMap | NV(7701xxx)→data-absent-reason | n/a | Problems | Mapped |  |
| eArrest.19-.22 | CPR/AED/Defib initiation timing + who first | O/R | No | Procedure | — | Procedure.performer / performedDateTime | mixed | — | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | Procedures* | Seeded | Note: eArrest.05/.06/.08 do not exist in 3.5 |
