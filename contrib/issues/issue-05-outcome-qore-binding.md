# eOutcome: QRPH "QORE" delegation has no linked binding or profile

**Summary.** The IG delegates outcome content (NEMSIS eOutcome — hospital
disposition, diagnoses, the closure of the EMS→hospital loop) to QRPH's
"QORE" work, but no binding, profile, or reference is linked. As it stands
the outcome loop is unrepresentable in mPSC terms: an implementer receiving
hospital outcome data has no target.

**Requests.**

1. Pin the QORE reference (document + version) or, if QORE isn't ready,
   state that explicitly so implementers know the gap is intentional.
2. Consider an interim representation in mPSC scope. We model outcomes as an
   Encounter + Observation cluster keyed to the EMS encounter and have a
   working closed loop in the open: hospital discharge events on either rail
   — ADT^A03 or a FHIR Discharge Summary document (LOINC 18842-5) — reduce
   to a common outcome record, match to the source PCR on conservative
   identity/timing/facility signals, and write back the NEMSIS eOutcome
   panel (XSD-valid output for state-registry resubmission).

Happy to share the matching heuristics and the eOutcome write-back rules as
input to the QORE/mPSC discussion.

Reference: <https://github.com/FHIRmedicConsulting/emsInterop>
(`src/emsinterop/outcome/`).
