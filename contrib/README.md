# Upstream contribution package — IHE PCC mPSC (Roadmap P7)

Everything needed to file the emsInterop mapping superset as a contribution
to the **IHE PCC mobile Paramedicine Summary of Care (mPSC)** IG, prepared
and evidence-checked; the actual filing is a human step (Chad's GitHub
identity, IHE's channels).

**Verification baseline:** every defect claim below was re-verified
**2026-08-07** against the mPSC **v2.0.0-draft CI build** (page footer
2025-10-30) at <https://build.fhir.org/ig/IHE/PCC.PCS/>. Source repo:
<https://github.com/IHE/PCC.PCS> (repo README: under construction; questions
to Andrea Fourquet). If the CI build has moved when filing, re-check the
three quick probes in `gap-report.md` first.

## What we are offering

| Artifact | Where | What it answers |
|---|---|---|
| Completed NEMSIS→FHIR field map | `fieldmap/*.md` + `fieldmap/nemsis-to-fhir-fieldmap.csv` (212 rows, 14 panels — generated from the S2T workbook by `scripts/export-fieldmap.py`) | The IG's NEMSIS-Mapping table is ~90% empty |
| Clean NEMSIS CodeSystem + 205 ValueSets + 7 ConceptMaps | `emsinterop.nemsis` FHIR package (release tarball, or `python -m emsinterop package-ig`) | The IG CodeSystem's 18 `TODO: JFM` placeholders and malformed codes |
| Proposed clinical Composition sections | `issues/issue-04-*.md`; implemented in `src/emsinterop/assemble/composition.py`, 0 errors through the official HL7 validator | The Composition's 3 mandatory sections leave most clinical panels homeless |
| Errata reconciliation vs NEMSIS 3.5.0 | `issues/issue-03-*.md` | Typos + missing elements in the mapping table |
| StructureMaps (FML) + logical models | `maps/structuremaps/`, `maps/logical/` | Executable form of the mapping, CI-checked against the reference Java engine |

## Filing plan

Draft issue texts live in `issues/` — one file per issue, title on the first
line, body ready to paste:

1. **issue-01** — the completed field map (the headline contribution)
2. **issue-02** — NEMSIS CodeSystem cleanup + offered replacement
3. **issue-03** — mapping-table errata (typos, missing elements, version pin)
4. **issue-04** — proposed clinical Composition sections
5. **issue-05** — eOutcome / QRPH "QORE" binding pin
6. **issue-06** — alignment & process (US Core note, release cadence, ITI bindings — the ITI item belongs on the EMS-Overall repo, noted inline)

Suggested order: file 01 first (it frames the rest), then 02–04 referencing
it; 05–06 are discussion-starters. Keep each issue self-contained — IG
editors triage independently.

## Regenerating

```sh
python scripts/export-fieldmap.py        # workbook -> contrib/fieldmap/
python -m emsinterop package-ig dist/pkg # the terminology package
```

The workbook (`docs/02_NEMSIS35_to_FHIR_S2T_Mapping.xlsx`) remains the
source of truth; edit there, re-export, commit both.
