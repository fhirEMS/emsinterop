"""nemsis2fhir — NEMSIS v3.5 ePCR XML -> IHE-conformant FHIR R4 translation engine.

Layered target (ADR-001): canonical US-Core-aligned resource graph (Layer A),
then the mPSC IPS document as a thin projection (Layer B). Output is submitted
to fhirEngine as a FHIR transaction Bundle (ADR-002/009).
"""

__version__ = "0.1.0"

MAPPING_RULESET_VERSION = "0.1.0"
"""Version stamped into Provenance / meta.tag for every generated resource."""
