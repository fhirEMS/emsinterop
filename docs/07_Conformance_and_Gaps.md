# Conformance and gaps — occupying what IHE left open

The IHE EMS profiles are two IGs, and between them they leave most of a working
translator undecided:

- **IHE PCC mPSC** (`ihe.pcc.mpsc`) is the content IG. Its NEMSIS→FHIR mapping
  table has an empty FHIR-path column on ~90–95% of rows, its NEMSIS CodeSystem
  carries 18 `TODO: JFM` placeholders, and its Composition profile defines three
  sections — none of them clinical beyond problems, allergies and medications.
- **IHE EMS-Overall** (`ihe.pcc.ems-overall`) is the workflow umbrella. It names
  no ITI transaction numbers and binds transport narratively.

An implementation that refused to act where the spec is silent would produce
nothing. So this project decides — and the decisions are defensible. What is
**not** defensible is letting them blur into conformance, because a consumer
validating against the IG reasonably expects our output to mean what the IG
says.

This document is the contract for that difference. It is enforced by
`tests/test_conformance.py`; the machine-readable form is
`src/emsinterop/conformance.py` and ships in every terminology package as
`conformance-gaps.json`.

---

## Rule 1 — Reference other people's canonicals; never publish at them

A `coding.system` may point anywhere. Pointing NEMSIS codes at
`https://profiles.ihe.net/PCC/mPSC/CodeSystem/NEMSIS` is exactly right: it is a
*reference*, and it means our data becomes conformant the day the IG is fixed,
with no migration.

Shipping a `CodeSystem` **resource** whose `url` is that canonical is a
different act entirely. It asserts we define that identifier. We do not. Two
conflicting definitions of one canonical break whichever terminology server
loads ours second — and until this policy landed, that is exactly what the
`emsinterop.nemsis` package did: 2,321 concepts published at the identifier
where IHE publishes 18 placeholders.

**What we do now**

| | |
|---|---|
| `coding.system` in emitted data | `https://profiles.ihe.net/PCC/mPSC/CodeSystem/NEMSIS` — unchanged |
| Published CodeSystem `url` | `<base>/CodeSystem/nemsis-registry` — ours |
| How the link is recorded | the published resource carries `identifier = <the mPSC canonical>` and a description saying what it stands in for and why |

This is deliberately **not** a `CodeSystem` supplement. Supplements add
designations and properties to a working code system; they do not stand in for
one that was never populated. Calling it a supplement would misrepresent what
we are doing.

## Rule 2 — Canonical URLs resolve; naming systems need not

A **canonical URL** identifies fetchable content — a profile, a value set, a
map. It belongs under a base we control and can serve, so an integrator (or an
IHE reviewer) can dereference it and find out what we meant.

A **naming system** — the `system` of an `identifier` or a `meta.tag` —
identifies no document at all. `urn:` is the honest form there, and these are
**not** migrated:

| Naming system | Why it must not move |
|---|---|
| `urn:emsinterop:resource-id` | Embedded in every conditional-update URL. Changing it stops matching resources already stored in a fhirEngine and silently duplicates the lot. Any change here is a data migration, not a rename. |
| `urn:emsinterop:mapping-ruleset` | The `meta.tag` scheme naming which ruleset produced a resource. Stable across ruleset versions by design — the *code* changes, the system does not. |

`submit/ids.py` also seeds its UUIDv5 namespace from the string
`urn:emsinterop`. That is not an identifier anyone sees; it is the salt that
makes resource ids deterministic. Changing it would change **every id this
project has ever produced**.

## The canonical base

```
https://fhirems.github.io/emsinterop/fhir
```

Everything derives from `conformance.CANONICAL_BASE`, so moving to a purchased
domain is one line plus a version bump. GitHub Pages under the org that already
hosts the code was chosen over `urn:` because `urn:` cannot be dereferenced,
which weakens an upstream submission and gives an implementer nothing to look
up.

**Migration rule if the base changes.** Old canonicals are retained as
`identifier` entries on the moved artifacts for one minor release, the change is
called out in `CHANGELOG.md` as identifier-affecting, and
`MAPPING_RULESET_VERSION` is bumped because emitted extension URLs change.

---

## The gap register

Seven entries, each verified against a **dated** build — these are CI builds and
they move, so an undated finding is a rumour. Every entry must answer three
questions, and the tests refuse it otherwise:

1. **What is open?** — with a citable source and the date it was checked.
2. **What do we do instead?** — and why that is defensible.
3. **What makes it go away?** — the retirement trigger. *A local decision with
   no retirement trigger is a permanent fork wearing a temporary label.*

| id | What IHE leaves open | What we do | Retires when |
|---|---|---|---|
| `mapping-table-empty` | FHIR-path column empty on ~90–95% of rows | Author the complete field map; every element Mapped/Seeded/Deferred, never dropped | IHE populates the column; ours becomes a conformance test against theirs |
| `composition-sections` | Three sections, none clinical beyond problems/allergies/meds; slicing is **open** | Emit LOINC-coded Vital Signs, Procedures, EMS Narrative, EMS Course sections — conformant, not a deviation | mPSC defines its own; where codes differ, theirs win |
| `nemsis-codesystem-placeholders` | 18 `TODO: JFM` concepts incl. malformed `99270235`, `C7`, `todo1` | Reference their canonical; publish our registry-derived concepts under ours | IHE publishes a usable CodeSystem; we drop ours, no coding changes |
| `outcome-delegated-to-qore` | eOutcome delegated to QRPH "QORE", which is named but not linked, bound or profiled | Interim Observation/Encounter cluster, marked interim | QORE is published with a binding; ours is **replaced, not merged** |
| `prior-care-vitals-flag` | `eVitals.02` (obtained before this unit's care) has no FHIR element and the IG proposes none | Project extension — a prior crew's reading is a different clinical claim | IHE or US Core defines an equivalent; dual-carry one release, then drop ours |
| `no-source-version-pin` | No NEMSIS version declared anywhere on the mapping page | Pin to 3.5.0, handle 3.5.1 as declared deltas | IHE pins a version; if not 3.5.0 that is a scope change, not a tweak |
| `transport-binding-loose` | EMS-Overall names no ITI transaction numbers | ITI-65 as the **default** binding behind a pluggable interface | EMS-Overall names its transactions; the default changes, the interface does not |

## Forward compatibility: dual-carry, then drop

When IHE fills a gap we occupy, we do **not** switch overnight and we do not
keep both forever. The pattern is the one ADR-006 already uses for US Core vs
`pcc-uv` race/ethnicity:

1. **Carry both** for one minor release, so consumers of either pass.
2. Mark ours deprecated in the register, with the release that removes it.
3. **Remove ours.** The register entry becomes a historical note.

Where the IG's choice and ours disagree, **theirs win** — the point of this
project is to conform to the standard, not to compete with it.

## What is enforced

`tests/test_conformance.py` fails the build if:

- any authored resource claims a canonical owned by HL7/IHE/SNOMED/LOINC/NLM;
- any authored canonical sits outside our base;
- the packaged CodeSystem claims the mPSC canonical, or fails to record which
  canonical it stands in for;
- emitted codings stop referencing the mPSC canonical (that would break the
  no-migration promise);
- any minted artifact has no entry in the gap register;
- any gap entry lacks a citable source, an ISO verification date, or a
  retirement trigger;
- the `resource-id` naming system changes, or diverges between the mapper and
  the bundle builder;
- an emitted local extension is not dereferenceable under our base.

## Re-verifying the register

The findings are dated because the sources move. Before relying on any entry —
and certainly before submitting anything upstream — re-probe:

```
NEMSIS-Mapping.html                          FHIR-path column density
CodeSystem-NEMSIS.html                       search "TODO: JFM"
StructureDefinition-IHE.PCC.FHIR.MS.Composition.html   section slice count
```

`contrib/gap-report.md` holds the longer prose version, including three findings
(element-id typos, missing elements, published-vs-master drift) that are errata
for IHE rather than gaps this project occupies.

> **Nothing in `contrib/` is published to IHE — or to any third party — without
> Chad's express permission, per submission.** This document describes what we
> would offer and why; it is not a dispatch queue.
