"""Deterministic resource identity (ADR-004).

UUIDv5 from (PCR key + panel + group index + element) makes re-submission
idempotent: a re-converted PCR updates the same resource ids in fhirEngine via
conditional update. Cross-PCR entities (Organization, Practitioner) derive
their id from their business identifier alone so they are shared across
submissions instead of duplicated.
"""

from __future__ import annotations

import uuid

NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:emsinterop")


def resource_id(*parts: str | int | None) -> str:
    """Deterministic UUIDv5 id from ordered discriminator parts."""
    key = "|".join("" if p is None else str(p) for p in parts)
    return str(uuid.uuid5(NAMESPACE, key))


def pcr_key(agency_number: str | None, pcr_number: str | None, pcr_uuid: str | None = None) -> str:
    """Stable key for one PatientCareReport. Prefers the NEMSIS UUID when the
    source emits one (per the NEMSIS V3 UUID Guide); falls back to
    agency + PCR number, which is unique within an agency."""
    if pcr_uuid:
        # Case-normalize: the NEMSIS UUID pattern is [a-fA-F0-9], so the SAME
        # record re-exported with different casing would otherwise key
        # differently, produce different UUIDv5 ids, and DUPLICATE in fhirEngine
        # instead of updating in place.
        return f"uuid:{pcr_uuid.strip().lower()}"
    if not (agency_number or pcr_number):
        raise ValueError(
            "cannot derive a stable PCR key: no UUID, agency number, or PCR number"
        )
    return f"pcr:{agency_number or ''}:{pcr_number or ''}"
