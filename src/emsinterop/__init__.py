"""emsinterop — NEMSIS v3.5 ePCR XML -> IHE-conformant FHIR R4 translation engine.

Layered target (ADR-001): canonical US-Core-aligned resource graph (Layer A),
then the mPSC IPS document as a thin projection (Layer B). Output is submitted
to fhirEngine as a FHIR transaction Bundle (ADR-002/009).
"""

from importlib import metadata as _metadata

try:
    __version__ = _metadata.version("emsinterop")
except _metadata.PackageNotFoundError:  # running from a source tree, uninstalled
    __version__ = "0.0.0.dev0"

MAPPING_RULESET_VERSION = "0.3.4"
"""Version stamped into Provenance / meta.tag for every generated resource.

Bump this whenever mapping SEMANTICS change, not merely when the package
version does — it is how a consumer tells which rules produced a resource.
0.3.1 covered the field-hardening changes: undated vitals carry date precision,
withheld US Core claims, off-scale glucose interpretations, and normalized
PCR UUIDs.

0.3.2 added a resource to the output: symptom onset (eSituation.01) with no
impression and no chief complaint now emits a standalone dated Observation
instead of being dropped, and eSituation.07/.08 are ledgered as explicit
deferrals when no Condition exists to carry an anatomic location.

0.3.3 changes an emitted extension URL. The `obtained-prior-to-unit-care`
extension moved from `urn:emsinterop:...` to this project's resolvable
canonical base, so a consumer can dereference what we invented. Codings are
untouched — NEMSIS still references the mPSC canonical — and the identifier
naming systems (`urn:emsinterop:resource-id`, `...:mapping-ruleset`) are
deliberately unchanged, because `resource-id` is embedded in every conditional
update URL. See docs/07_Conformance_and_Gaps.md.

0.3.4 changes every address this project emits. `Address.state` carried the
NEMSIS ANSI/FIPS code (`49`) where FHIR asks for an abbreviation and US Core
binds to USPS two-letter codes (`UT`); `Address.city` carried a GNIS feature id
(`1454997`) where FHIR asks for "Name of city, town etc.". Both are `string`
and the binding is `extensible`, so both validated while being the wrong
vocabulary — and a receiving system displays them verbatim. State now resolves;
city is populated only from a supplied gazetteer, with the GNIS id preserved in
an extension so the NEMSIS round trip stays exact.
"""
