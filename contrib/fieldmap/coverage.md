# Coverage Matrix — status counts per panel (live COUNTIF over each tab)

| Panel tab | Primary FHIR target(s) | Mapped | Seeded | Deferred | Upstream | Total rows |
|---|---|---|---|---|---|---|
| Admin_Org_Crew | Composition/Organization/Practitioner/Provenance | =COUNTIF(Admin_Org_Crew!$M:$M,"Mapped") | =COUNTIF(Admin_Org_Crew!$M:$M,"Seeded") | =COUNTIF(Admin_Org_Crew!$M:$M,"Deferred") | =COUNTIF(Admin_Org_Crew!$M:$M,"Upstream") | =SUM(C4:F4) |
| Encounter | Encounter (spine) / Location | =COUNTIF(Encounter!$M:$M,"Mapped") | =COUNTIF(Encounter!$M:$M,"Seeded") | =COUNTIF(Encounter!$M:$M,"Deferred") | =COUNTIF(Encounter!$M:$M,"Upstream") | =SUM(C5:F5) |
| ePatient | Patient (US Core / IHE PCC) | =COUNTIF(ePatient!$M:$M,"Mapped") | =COUNTIF(ePatient!$M:$M,"Seeded") | =COUNTIF(ePatient!$M:$M,"Deferred") | =COUNTIF(ePatient!$M:$M,"Upstream") | =SUM(C6:F6) |
| eSituation_eInjury | Condition / Observation | =COUNTIF(eSituation_eInjury!$M:$M,"Mapped") | =COUNTIF(eSituation_eInjury!$M:$M,"Seeded") | =COUNTIF(eSituation_eInjury!$M:$M,"Deferred") | =COUNTIF(eSituation_eInjury!$M:$M,"Upstream") | =SUM(C7:F7) |
| eArrest | Observation / Procedure | =COUNTIF(eArrest!$M:$M,"Mapped") | =COUNTIF(eArrest!$M:$M,"Seeded") | =COUNTIF(eArrest!$M:$M,"Deferred") | =COUNTIF(eArrest!$M:$M,"Upstream") | =SUM(C8:F8) |
| eHistory | Condition / Allergy / MedicationStatement / Consent | =COUNTIF(eHistory!$M:$M,"Mapped") | =COUNTIF(eHistory!$M:$M,"Seeded") | =COUNTIF(eHistory!$M:$M,"Deferred") | =COUNTIF(eHistory!$M:$M,"Upstream") | =SUM(C9:F9) |
| eVitals | Observation (US Core Vital Signs) | =COUNTIF(eVitals!$M:$M,"Mapped") | =COUNTIF(eVitals!$M:$M,"Seeded") | =COUNTIF(eVitals!$M:$M,"Deferred") | =COUNTIF(eVitals!$M:$M,"Upstream") | =SUM(C10:F10) |
| eMedications | MedicationAdministration | =COUNTIF(eMedications!$M:$M,"Mapped") | =COUNTIF(eMedications!$M:$M,"Seeded") | =COUNTIF(eMedications!$M:$M,"Deferred") | =COUNTIF(eMedications!$M:$M,"Upstream") | =SUM(C11:F11) |
| eProcedures_eAirway | Procedure | =COUNTIF(eProcedures_eAirway!$M:$M,"Mapped") | =COUNTIF(eProcedures_eAirway!$M:$M,"Seeded") | =COUNTIF(eProcedures_eAirway!$M:$M,"Deferred") | =COUNTIF(eProcedures_eAirway!$M:$M,"Upstream") | =SUM(C12:F12) |
| eExam_eLabs_eDevice | Observation / DiagnosticReport / Media | =COUNTIF(eExam_eLabs_eDevice!$M:$M,"Mapped") | =COUNTIF(eExam_eLabs_eDevice!$M:$M,"Seeded") | =COUNTIF(eExam_eLabs_eDevice!$M:$M,"Deferred") | =COUNTIF(eExam_eLabs_eDevice!$M:$M,"Upstream") | =SUM(C13:F13) |
| eDisposition | Encounter / Location / Communication | =COUNTIF(eDisposition!$M:$M,"Mapped") | =COUNTIF(eDisposition!$M:$M,"Seeded") | =COUNTIF(eDisposition!$M:$M,"Deferred") | =COUNTIF(eDisposition!$M:$M,"Upstream") | =SUM(C14:F14) |
| ePayment | Coverage / Contract | =COUNTIF(ePayment!$M:$M,"Mapped") | =COUNTIF(ePayment!$M:$M,"Seeded") | =COUNTIF(ePayment!$M:$M,"Deferred") | =COUNTIF(ePayment!$M:$M,"Upstream") | =SUM(C15:F15) |
| eOutcome | (external QORE) — deferred | =COUNTIF(eOutcome!$M:$M,"Mapped") | =COUNTIF(eOutcome!$M:$M,"Seeded") | =COUNTIF(eOutcome!$M:$M,"Deferred") | =COUNTIF(eOutcome!$M:$M,"Upstream") | =SUM(C16:F16) |
| eNarrative_eOther | Composition.text / DocumentReference / Provenance | =COUNTIF(eNarrative_eOther!$M:$M,"Mapped") | =COUNTIF(eNarrative_eOther!$M:$M,"Seeded") | =COUNTIF(eNarrative_eOther!$M:$M,"Deferred") | =COUNTIF(eNarrative_eOther!$M:$M,"Upstream") | =SUM(C17:F17) |
| TOTAL | all national panels | =SUM(C4:C17) | =SUM(D4:D17) | =SUM(E4:E17) | =SUM(F4:F17) | =SUM(G4:G17) |
| Note: | Row counts are mapping ROWS; many rows cover an element RANGE (e.g. eExam.04-.25, eInjury.11-.29), so covered NEMSIS elements far exceed row counts. 'Deferred' concentrates in eOutcome (→QORE), billing (ePayment), and telematics/waveforms (ACN, eDevice, eLabs imaging) — all intentional, none silently dropped. |  |  |  |  |  |
