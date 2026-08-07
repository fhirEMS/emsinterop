# eNarrative · eOther → Composition.text / DocumentReference / Provenance

Panel tab `eNarrative_eOther` of the NEMSIS 3.5.0 → FHIR R4 source-to-target workbook (emsInterop). Status column: Mapped = full target defined · Seeded = target assigned · Deferred = intentionally postponed (ledgered, never dropped).

| NEMSIS ID | NEMSIS Element Name | Usage/Card | Repeats | Target FHIR Resource | Target Profile | FHIR Path | Datatype Transform | Terminology / ConceptMap | NV handling | PN handling | mPSC Section | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eNarrative.01 | Patient Care Report Narrative | RE [0..1] | No | Composition / DocumentReference | — | Composition.section.text (EMS narrative) + DocumentReference | string→narrative | n/a | NV(7701xxx)→data-absent-reason | n/a | EMS Narrative* | Mapped | Free-text; proposed dedicated section |
| eOther.01-.02 | Review Requested / System-of-Care Registry Patient | O | No | Flag / Observation | — | Flag / Observation | code | — | NV(7701xxx)→data-absent-reason | n/a | (header) | Seeded |  |
| eOther.03 | Personal Protective Equipment Used | O | No | Observation | — | Observation | code | ConceptMap | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | (header) | Seeded | Crew safety |
| eOther.04-.08 | Crew member IDs / work-related exposure / disaster / report author | O/RE | No | Practitioner / Observation / Provenance | — | Provenance.agent; Observation (exposure) | mixed | — | NV(7701xxx)→data-absent-reason | PN(8801xxx)→statusReason/negation | (header) | Seeded |  |
| eOther.09-.11 | External Electronic Document / File Attachment Type + Image | O | Yes | DocumentReference / Media | — | DocumentReference.content.attachment / Media | base64/url | MIME | NV(7701xxx)→data-absent-reason | n/a | (header) | Mapped | 12-lead PDFs, images |
| eOther.12-.21 | Signature block (type/reason/representative/status/graphic/name/time) | O | Yes | Provenance / DocumentReference | — | Provenance.signature | signature | — | NV(7701xxx)→data-absent-reason | n/a | (header) | Seeded | Src typo: 'deOther.21'→eOther.21 |
| eOther.22 | File Attachment Name | O | No | DocumentReference | — | DocumentReference.content.attachment.title | string | n/a | NV(7701xxx)→data-absent-reason | n/a | (header) | Mapped |  |
