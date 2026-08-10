# Test corpora — all data is SYNTHETIC

Nothing in this directory is real patient data. Every name, address, phone
number, date of birth, and identifier was invented for testing. No PHI has ever
been committed to this repository, and none should be: the project runs on
synthetic data only until the production gates in `docs/05_Operations.md` §1
are met.

Three corpora, each answering a different question:

| Directory | Question it answers |
|---|---|
| `pcr_*.xml` (golden) | Does the mapper produce correct, conformant FHIR for cases we designed — NV/PN, negation, repeating groups, arrest, MCI, interfacility, pediatric, refusal? |
| `hostile/` | Does it survive XSD-**valid** input that broke it once — a palpated BP, an off-scale glucose, a comment inside a value, a refused sex, a URL-hostile PCR number? See that directory's README. |
| `hl7v2/`, `fhir/` | Does the inbound outcome loop match and write back correctly from either discharge rail? |

A fourth, *discovery* tier lives outside the repo: point `EMSINTEROP_SAMPLES`
at published NEMSIS scenario samples (`tests/test_nemsis_samples.py`). When it
finds something new, distil it into a minimal `hostile/` fixture so default CI
catches it forever after.
