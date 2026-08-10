# Upstream contribution package — IHE PCC mPSC (Roadmap P7)

The emsInterop mapping superset prepared as a contribution to the **IHE PCC
mobile Paramedicine Summary of Care (mPSC)** IG, evidence-checked and
channel-neutral. **Policy: no issues will be opened in IHE (or any
third-party) repositories.** The proposals are standalone documents; whether
and how they are sent is Chad's call.

**Verification baseline:** every defect claim below was re-verified
**2026-08-07** against the mPSC **v2.0.0-draft CI build** (page footer
2025-10-30) at <https://build.fhir.org/ig/IHE/PCC.PCS/>. If the CI build has
moved when submitting, re-check the three quick probes in `gap-report.md`
first.

## What we are offering

| Artifact | Where | What it answers |
|---|---|---|
| Completed NEMSIS→FHIR field map | `fieldmap/*.md` + `fieldmap/nemsis-to-fhir-fieldmap.csv` (212 rows, 14 panels — generated from the S2T workbook by `scripts/export-fieldmap.py`) | The IG's NEMSIS-Mapping table is ~90% empty |
| Clean NEMSIS CodeSystem + 205 ValueSets + 7 ConceptMaps | `emsinterop.nemsis` FHIR package (release tarball, or `python -m emsinterop package-ig`) | The IG CodeSystem's 18 `TODO: JFM` placeholders and malformed codes |
| Proposed clinical Composition sections | `issues/issue-04-*.md`; implemented in `src/emsinterop/assemble/composition.py`, 0 errors through the official HL7 validator | The Composition's 3 mandatory sections leave most clinical panels homeless |
| Errata reconciliation vs NEMSIS 3.5.0 | `issues/issue-03-*.md` | Typos + missing elements in the mapping table |
| StructureMaps (FML) + logical models | `maps/structuremaps/`, `maps/logical/` | Executable form of the mapping, CI-checked against the reference Java engine |

## The proposals

Six standalone documents in `proposals/` — title on the first line, body
self-contained, no channel assumed:

1. **proposal-01** — the completed field map (the headline contribution)
2. **proposal-02** — NEMSIS CodeSystem cleanup + offered replacement
3. **proposal-03** — mapping-table errata (typos, missing elements, version pin)
4. **proposal-04** — proposed clinical Composition sections
5. **proposal-05** — eOutcome / QRPH "QORE" binding pin
6. **proposal-06** — alignment & process (US Core note, release cadence, ITI bindings — includes an EMS-Overall concern, with a note asking the editors to route it)

## Channels — for reference only, none to be used without express permission

If and when Chad authorizes a specific submission, these are the routes:

- **Direct email** to the IHE PCC Technical Committee / the mPSC editor
  (the IG repo names Andrea Fourquet as contact), with the proposals
  attached or this directory linked once public.
- **IHE's public-comment process** (ihe.net) when the IG next opens a
  comment period — proposals 03/05/06 fit that format directly.
- **chat.fhir.org** — the implementers' Zulip has IHE-adjacent streams;
  a summary post linking here starts the conversation without any filing.
- **Passive publication** — NOTE: the repository went public on 2026-08-09, so
  this directory is now world-readable whether or not anyone points to it.
  That is a consequence of the repo's visibility, not a decision to publish;
  if the material should not be discoverable, it has to move out of the public
  repo (and note that git history is already public).

proposal-01 doubles as the cover letter for any of these.

## Regenerating

```sh
python scripts/export-fieldmap.py        # workbook -> contrib/fieldmap/
python -m emsinterop package-ig dist/pkg # the terminology package
```

The workbook (`docs/02_NEMSIS35_to_FHIR_S2T_Mapping.xlsx`) remains the
source of truth; edit there, re-export, commit both.
