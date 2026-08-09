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

MAPPING_RULESET_VERSION = "0.3.1"
"""Version stamped into Provenance / meta.tag for every generated resource.

Bump this whenever mapping SEMANTICS change, not merely when the package
version does — it is how a consumer tells which rules produced a resource.
0.3.1 covers the field-hardening changes: undated vitals carry date precision,
withheld US Core claims, off-scale glucose interpretations, and normalized
PCR UUIDs.
"""
