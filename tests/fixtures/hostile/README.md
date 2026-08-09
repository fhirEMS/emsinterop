# Hostile corpus — XSD-valid input the mapper must survive

Every file here **passes** the pinned NEMSIS 3.5.0 schema. That is the point:
these are documents the ingest gate lets through, carrying traits our own
six-case golden corpus never exercised. XSD-*invalid* input belongs with the
quarantine tests in `test_ingest.py` / `test_serve.py` instead.

Each fixture is `pcr_refusal.xml` with one targeted mutation, so a diff against
that file shows exactly the hostile trait and nothing else. Each has its own
`eRecord.01` and `PatientCareReport UUID` so bronze landing and deterministic
ids never collide.

| Fixture | Pins |
|---|---|
| `hostile_comment_in_value.xml` | A comment inside a valued leaf. lxml counts comments as children and puts following text in the comment's `tail`, so a naive parser reads an empty group and the reading **vanishes with no ledger entry** — a breach of the never-silently-drop rule. |
| `hostile_vitals_no_time.xml` | `eVitals.01` nil+NV. `effective[x]` must be **omitted entirely**: a value-less primitive trips invariant `vs-1`, which the validator applies on the strength of `category=vital-signs`, not `meta.profile`. |
| `hostile_sex_refused.xml` | `ePatient.25` nil+PN (refused). `us-core-patient` requires `gender` min=1, which a data-absent extension does not satisfy — so the claim is **withheld**, and we never substitute `unknown`. |
| `hostile_glucose_high.xml` | `eVitals.18` = `High`. XSD-sanctioned off-scale meter reading; recorded as interpretation `HX`, not flattened to "malformed data". |
| `hostile_url_unsafe_id.xml` | A PCR number containing space, `/`, `&`, `?`, `#`. `eRecord.01` is `xs:string` with no pattern, so these must be escaped in conditional-update URLs — unescaped, the search truncates and could match the **wrong** resource. |
| `hostile_uppercase_uuid.xml` | An uppercase `PatientCareReport/@UUID`. The NEMSIS pattern is `[a-fA-F0-9]`, so the same record re-exported with different casing must still produce the **same** ids and update in place rather than duplicate. |

Discovered by running real NEMSIS scenario samples (`EMSINTEROP_SAMPLES`, see
`tests/test_nemsis_samples.py`). When that discovery tier finds something new,
distil it into a minimal fixture here so default CI catches it forever after.
