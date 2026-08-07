# Terminology & ConceptMap Strategy

| NEMSIS source | Mechanism | FHIR target system | Approach | ConceptMap id (proposed) | Notes |
|---|---|---|---|---|---|
| Provider Impression (eSituation.11/.12) | ICD-10-CM in source [corrected 2026-08-06: 3.5.0 XSD pattern-verified; was 'SNOMED in source'] | http://hl7.org/fhir/sid/icd-10-cm | Pass-through (validate only) | — | ICD-10-CM-coded in 3.5.0 (impressions moved off SNOMED); assign system, do not re-code |
| Procedure (eProcedures.03) | SNOMED in source | http://snomed.info/sct | Pass-through | — | Airway/vascular/CPR procedures |
| Medication (eMedications.03) | RxNorm in source | http://www.nlm.nih.gov/research/umls/rxnorm | Pass-through | — |  |
| Injury cause / diagnosis | ICD-10-CM in source | http://hl7.org/fhir/sid/icd-10-cm | Pass-through | — |  |
| Route of administration (eMedications.04, 9927xxx) | NEMSIS numeric | SNOMED route (+NEMSIS secondary) | ConceptMap + dual-code | cm-nemsis-medroute | e.g. 9927023 IV → 47625008 |
| MCI triage color (eScene.08, 2708xxx) | NEMSIS numeric | SNOMED / local | ConceptMap | cm-nemsis-triage | Red/Yellow/Green/Black (START/SALT) |
| Cardiac rhythm (eVitals.03, eArrest.11/.17) | NEMSIS numeric | SNOMED | ConceptMap | cm-nemsis-rhythm | Asystole/VF/VT/PEA/etc. |
| Response mode / priority (eResponse.23, eDisposition.17) | NEMSIS numeric | Encounter priority ActCode | ConceptMap | cm-nemsis-priority | Emergent/non-emergent |
| Level of service (dAgency.11, eDisposition.32) | NEMSIS numeric | SNOMED / local | ConceptMap | cm-nemsis-los | ALS/BLS/Paramedic (4232xxx) |
| AVPU (eVitals.26) | NEMSIS numeric | SNOMED | ConceptMap | cm-nemsis-avpu |  |
| Race (ePatient.14) | OMB categories | CDC Race&Ethnicity + US Core | ConceptMap | cm-nemsis-race | Dual-carry US Core us-core-race + mPSC pcc-uv-race (ADR-006) |
| Admin sex (ePatient.25 Sex; .13 legacy) | NEMSIS numeric | FHIR administrative-gender + US Core birthsex | ConceptMap | cm-nemsis-sex | Prefer .25; .13 fallback (ADR-007) |
| Not-Values NV (7701xxx) | xsi:nil + NV attr | http://.../data-absent-reason | ConceptMap → DAR | cm-nemsis-nv | 7701001→not-applicable · 7701003→unknown/not-recorded · 7701005→masked |
| Pertinent-Negatives PN (8801xxx) | PN attr | statusReason / negation | ConceptMap → negation | cm-nemsis-pn | 8801013 No Known Drug Allergy → negated AllergyIntolerance; 8801001 contraindicated → MedAdmin.statusReason |
| Any NEMSIS code without standard target | NEMSIS numeric | https://profiles.ihe.net/PCC/mPSC/CodeSystem/NEMSIS (LOCAL clean copy) | Retain as secondary coding | — | Own a clean local CodeSystem — IG copy has ~13 TODO/placeholder concepts + 1 malformed entry |
