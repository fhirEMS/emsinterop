"""FHIR transaction Bundle builder.

Idempotent resubmission (ADR-004/009) via CONDITIONAL update: fhirEngine has
no update-as-create (plain PUT to a nonexistent id 404s), but its
`PUT Type?<search>` is a true upsert — 0 matches create (preserving our
deterministic client id, so literal references stay valid), 1 match updates.
Every resource carries a deterministic resource-id identifier as the match
key; Provenance (no identifier element in R4) matches on its Patient target,
Composition on its PCR business identifier. fhirEngine is the ONLY writer of
FHIR storage — this bundle over its REST API is the seam.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

RESOURCE_ID_SYSTEM = "urn:emsinterop:resource-id"


def _stamp_provenance_recorded(resources: list[dict], recorded: str | None) -> None:
    stamp = recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")
    for resource in resources:
        if resource["resourceType"] == "Provenance" and "recorded" not in resource:
            resource["recorded"] = stamp


def _conditional_url(resource: dict) -> str:
    """Conditional-update URL for a resource (the idempotency key)."""
    resource_type = resource["resourceType"]
    if resource_type == "Provenance":
        patient_targets = [
            t["reference"]
            for t in resource.get("target", [])
            if t.get("reference", "").startswith("Patient/")
        ]
        if patient_targets:
            return f"Provenance?target={quote(patient_targets[0], safe='/')}"
        return f"Provenance/{resource['id']}"  # last resort: plain PUT
    if resource_type == "Composition":
        business = resource.get("identifier") or {}
        if business.get("value"):
            # Escape the VALUE only: eRecord.01 is xs:string with no pattern,
            # so a PCR number may contain / & ? # — unescaped, those would
            # truncate the search and could match the WRONG Composition. The
            # system is our own literal urn:/http: constant and stays readable.
            return (
                f"Composition?identifier={business.get('system', '')}"
                f"|{quote(business['value'], safe='')}"
            )
    for identifier in resource.get("identifier", []):
        if identifier.get("system") == RESOURCE_ID_SYSTEM:
            return (f"{resource_type}?identifier={RESOURCE_ID_SYSTEM}"
                    f"|{quote(identifier['value'], safe='')}")
    return f"{resource_type}/{resource['id']}"


def transaction_bundle(
    resources: list[dict],
    bundle_identifier: str | None = None,
    recorded: str | None = None,
) -> dict:
    """Build a transaction Bundle over the mapper's in-memory graph."""
    _stamp_provenance_recorded(resources, recorded)
    bundle: dict = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "fullUrl": f"urn:uuid:{resource['id']}",
                "resource": resource,
                "request": {
                    "method": "PUT",
                    "url": _conditional_url(resource),
                },
            }
            for resource in resources
        ],
    }
    if bundle_identifier:
        bundle["identifier"] = {
            "system": "urn:nemsis:identifier:pcr",
            "value": bundle_identifier,
        }
    return bundle
