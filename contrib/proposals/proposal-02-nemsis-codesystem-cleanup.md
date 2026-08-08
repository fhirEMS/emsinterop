# NEMSIS CodeSystem: 18 placeholder/malformed concepts; cleaned replacement offered

**Summary.** `CodeSystem-NEMSIS.html` (v2.0.0-draft CI build, canonical
`https://profiles.ihe.net/PCC/mPSC/CodeSystem/NEMSIS`) contains 18 concepts
whose display is a `TODO: JFM …` placeholder, including three malformed
entries that do not appear in any NEMSIS enumeration:

- `99270235` — "TODO: JFM some drug, I think" (not a valid NEMSIS code shape)
- `C7` — "TODO: JFM odd one"
- `todo1` — "TODO: JFM missing code"

plus placeholder displays on otherwise-valid codes (3009001, 9925005,
9923003, 3105011, 4218001/007/013, 9916001/003, 3907033, 3913019, 4219001,
4216005, 4214017, 9922001–9922005). Runtime terminology validation cannot
depend on the CodeSystem in this state.

**Offer.** We maintain a clean NEMSIS 3.5.0 code registry extracted from the
official element enumeration tables, published as a FHIR package
(`emsinterop.nemsis`):

- `CodeSystem` on the IG's canonical URL — 2,321 concepts, official display
  text, `content: fragment` (it carries the nationally-mapped elements'
  codes, honestly declared as a subset rather than claiming completeness);
- 205 per-element `ValueSet`s (enumerated `compose`, expansion-ready);
- 7 `ConceptMap`s to standard vocabularies (administrative-gender, US Core
  birthsex, CDC Race & Ethnicity, SNOMED routes, NUBC discharge status,
  v3-ActPriority, data-absent-reason) with explicit `equivalence` on every
  row (`equivalent` vs `wider` — the `wider` rows are deliberately marked so
  consumers don't reverse them).

We'd gladly PR the cleaned CodeSystem (and ValueSets/ConceptMaps if wanted)
into the IG source, or hand over the generator.

Package: release tarballs at
<https://github.com/fhirEMS/emsinterop/releases>
(`emsinterop.nemsis-<version>.tgz`); regenerable via
`python -m emsinterop package-ig <dir>`.
