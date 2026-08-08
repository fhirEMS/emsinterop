# Proposal: clinical sections for the mPSC Composition (vitals, procedures, EMS course, narrative)

**Summary.** The Medical Summary Composition profile
(`StructureDefinition-IHE.PCC.FHIR.MS.Composition.html`, v2.0.0-draft)
mandates three sections — Problems (11450-4), Allergies (48765-2),
Medications — with open slicing. A paramedicine summary's clinically
decisive content (vital-sign trends, interventions performed, the course of
the call) has no defined home, so every implementer invents ad-hoc sections
and consumers can't rely on placement.

**Proposal.** Add optional defined section slices:

| Section | LOINC | Entries |
|---|---|---|
| Vital Signs | 8716-3 | Observation (vital-signs category; one per VitalGroup measurement, group timestamp preserved) |
| Procedures | 47519-4 | Procedure (incl. negated/refused procedures — PN semantics) |
| EMS Course | 46240-8 | Encounter + response/disposition Observations (the operational facts of the call) |
| EMS Narrative | 28568-4 | The eNarrative text (section.text; no coded entries) |

Rationale for optional-not-mandatory: a prearrival/at-the-door snapshot may
legitimately lack some sections; `emptyReason` covers panels present in the
source but empty (including the NEMSIS NV escalation — e.g. "Not Recorded"
→ `notasked`).

**Implementation evidence.** These sections are implemented in the
open-source emsInterop engine alongside the IG's three: a six-case golden
corpus of documents (cardiac arrest, MCI, interfacility, pediatric,
refusal, chest pain) validates with **0 errors** through the official HL7
validator, sections populated from real NEMSIS panels including the
NV/PN edge cases. We can contribute the slice definitions as FSH/SD PRs if
the direction is agreeable.

Reference: <https://github.com/fhirEMS/emsinterop>
(`src/emsinterop/assemble/composition.py`, golden corpus under `tests/`).
