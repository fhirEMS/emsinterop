# Plan — `nemsynth`: a Synthea-equivalent generator for NEMSIS

## Why

Five published NEMSIS scenario samples found nine real defects that six
self-authored fixtures never could. That is the whole argument: **our corpus
only proves the mapper handles what we thought of.** Real agency exports are not
yet available, so the next best thing is a generator that produces NEMSIS
documents *nobody on this project designed*, in volume, with the messiness real
data has.

Synthea is the right reference point — statistically plausible synthetic
patients, freely shareable, no PHI — but it models longitudinal primary care and
emits FHIR/C-CDA. Nothing about its output is a NEMSIS ePCR: no dispatch, no
response times, no crew, no scene, no NV/PN semantics, no state-registry shape.
This is the EMS-shaped equivalent, not a Synthea plug-in.

## What it is

A separate package, `nemsynth`, that emits **XSD-valid NEMSIS 3.5.0/3.5.1
EMSDataSet documents** with no dependency on emsInterop. That independence is
the point: a generator that imported our mapper's assumptions would only ever
generate what our mapper already handles, which is exactly the blind spot we are
trying to escape. It is a *producer* of the standard; emsInterop is a
*consumer*. They should agree only through the XSD.

Deliberately **not** in this repo, and not a test fixture factory. Fixtures pin
known behaviour and must stay hand-reviewable; this generates volume and
surprise. Its output feeds the discovery tier (`EMSINTEROP_SAMPLES`), and
anything it breaks gets distilled into a minimal hostile fixture here.

## Design

### 1. Clinical scenarios, not random fields

Random values inside a schema produce documents that are valid and clinically
nonsense — they find crashes but not mapping errors. Generation is
**scenario-driven**: a small library of EMS presentations (cardiac arrest, STEMI,
stroke, OD/naloxone, MVC trauma, respiratory distress, psychiatric/behavioral,
OB, pediatric febrile seizure, refusal, standby/no-patient, interfacility
transfer, MCI with multiple patients), each a state machine over the call:

```
dispatch → response → arrival → assessment → intervention(s) → transport → outcome
```

Each stage samples from distributions conditioned on the scenario, so a cardiac
arrest yields arrest elements, CPR/defib procedures, epinephrine, a ROSC-or-not
branch, and a disposition consistent with all of it. Internal consistency is a
first-class requirement: a patient who refused transport must not carry a
destination hospital; a pediatric call must have age-appropriate vitals.

### 2. Realistic imperfection — the highest-value part

Real ePCRs are incomplete and untidy. A generator that emits only clean, fully
populated records would be *less* useful than the samples we already have. Each
generated document gets a configurable "messiness profile":

- **NV/PN** applied at realistic rates per element — this is the project's #1
  correctness trap and must be exercised in bulk, not in six curated cases.
- **Missing optional panels** — most calls have no labs, no devices, no arrest.
- **The sentinels**: `eVitals.07` P/p (palpated BP), `eVitals.18` High/Low.
- **Free-text oddities** in unconstrained `xs:string` fields — narratives with
  quotes, ampersands, newlines; PCR numbers with slashes and spaces (which found
  a path traversal here).
- **Boundary values**: hour-24 timestamps, age 0 and 120, empty repeating groups,
  maximum-length strings, mixed UTC offsets within one call.
- **Multi-PCR files** and multi-patient MCI incidents.

Every knob is seeded and reproducible: `nemsynth --seed 42` must produce byte-
identical output forever, or a regression found today cannot be replayed
tomorrow.

### 3. Correct by construction

The generator validates its own output against the pinned XSD before writing.
A generator that emits invalid NEMSIS teaches the consumer nothing — every
finding would be ambiguous between "generator bug" and "mapper bug". Anything
that fails its own gate is a generator defect, full stop.

### 4. Demographic plausibility without PHI

Names, addresses and phone numbers come from public synthetic sources (census
surname/given frequency lists, a synthetic address pool). No real person's data,
and the README says so as loudly as `tests/fixtures/README.md` does here.

## Phases

| Phase | Deliverable | Value |
|---|---|---|
| **1** | One scenario (chest pain) end-to-end, XSD-valid, seeded, CLI: `nemsynth gen --scenario chest-pain --seed 1 -o out/` | Proves the skeleton; immediately usable in the discovery tier |
| **2** | The messiness engine (NV/PN rates, sentinels, boundaries, free-text) | Where the defects actually live |
| **3** | The scenario library (12–15 presentations) + MCI multi-patient | Breadth of clinical shape |
| **4** | Volume + a corpus-sweep harness: generate N, convert all, report every crash/unmapped-national-element/validator error, ranked | Turns the generator into a *fuzzing* loop against the mapper |
| **5** | DEMDataSet generation (agency/crew/vehicle rosters) | Exercises the demographics rail, which today has one fixture |

Phase 4 is the real prize: a nightly loop generating thousands of documents and
reporting only what breaks. That is how the remaining unknown-unknowns surface
without waiting for a real agency export.

## How it plugs in

```sh
nemsynth gen --count 500 --seed 7 --messiness high -o /tmp/synth
EMSINTEROP_SAMPLES=/tmp/synth python -m pytest tests/test_nemsis_samples.py
```

The existing discovery tier already asserts exactly the right invariants —
XSD-valid, converts without raising, no national element unmapped, every issue
informational — so it needs **no changes** to consume generated input. That is a
deliberate consequence of how that tier was built.

## Open questions for Chad

1. **Repo**: separate `fhirEMS/nemsynth` (my recommendation — independence is
   the design), or a subdirectory here?
2. **License/publishing**: a public synthetic NEMSIS generator would be genuinely
   novel; nothing comparable exists publicly. Is that a goal, or internal-only?
3. **Fidelity ceiling**: statistically plausible (distributions roughly matching
   NEMSIS public research data) or merely clinically coherent? The former is
   substantially more work and matters mainly if the output will also be used for
   analytics/ML demos rather than only for testing the mapper.
