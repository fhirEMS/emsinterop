# NEMSIS-Mapping.html errata: element-id typos, missing elements, no version pin

Verified against the v2.0.0-draft CI build (2026-08-07). Three independent
fixes, filed together because they all concern the mapping table's use as a
machine-consumable inventory:

**1. Element-id typos**

| In the table | Should be |
|---|---|
| `deDisposition.15` ("How Patient Was Moved From Ambulance") | `eDisposition.15` |
| `deOther.21` ("Signature First Name") | `eOther.21` |
| `EPSAP Call Date/Time` (eTimes.01 label) | "PSAP Call Date/Time" |

The stray `d` prefix collides with the DEMDataSet namespace (dAgency.*,
dConfiguration.*), so automated consumers mis-bucket these rows.

**2. Missing elements** — the table skips national elements that exist in
the NEMSIS v3.5.0 data dictionary:

- `eResponse.15` (table jumps eResponse.14 → eResponse.16)
- `eArrest.05`, `eArrest.06`, `eArrest.08` (jumps .04 → .07 → .09)
- ePayment rows appear out of dictionary order mid-panel

A full reconciliation against the 3.5.0 dictionary is available (the
complete field map offered in the companion issue covers every national
element per panel).

**3. No NEMSIS version declared.** The mapping page never states which
NEMSIS release it maps (3.4 / 3.5.0 / 3.5.1 differ materially — e.g.
ePatient.13 Gender is deprecated in favor of ePatient.25 Sex in 3.5.0+).
Request: declare the source version on the page, ideally pinned to a
data-dictionary release. Our map is scoped to 3.5.0 with 3.5.1 deltas
flagged, if useful as a reference.
