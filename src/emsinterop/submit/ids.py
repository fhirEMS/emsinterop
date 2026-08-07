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
        return f"uuid:{pcr_uuid}"
    return f"pcr:{agency_number}:{pcr_number}"
