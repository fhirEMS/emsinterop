"""ITI-65 Provide Document Bundle (MHD) — the mPSC handoff package.

Wraps the assembled mPSC FHIR document in the MHD Minimal-Metadata shape
(Architecture §5.7, ADR-008): a transaction Bundle carrying

  1. a SubmissionSet (`List` with the MHD SubmissionSet profile),
  2. a `DocumentReference` describing the document (type mirrors the mPSC
     Composition type, LOINC 107903-7),
  3. a `Binary` holding the document Bundle itself (application/fhir+json).

Built from the mapper's in-memory ConversionResult — the same no-read-back
rule as document assembly (§5.5a). Deterministic ids (UUIDv5 off the PCR key)
keep resubmissions diffable; `submitted_at` defaults to the Composition date
so golden-corpus output is reproducible — real senders pass the actual
submission time.
"""

from __future__ import annotations

import base64
import json

from ..submit import ids
from ..terminology import systems

MHD_SUBMISSIONSET_PROFILE = (
    "https://profiles.ihe.net/ITI/MHD/StructureDefinition/IHE.MHD.Minimal.SubmissionSet"
)
MHD_DOCUMENTREFERENCE_PROFILE = (
    "https://profiles.ihe.net/ITI/MHD/StructureDefinition/IHE.MHD.Minimal.DocumentReference"
)
MHD_PROVIDE_BUNDLE_PROFILE = (
    "https://profiles.ihe.net/ITI/MHD/StructureDefinition/IHE.MHD.Minimal.ProvideBundle"
)
MHD_LIST_TYPES = "https://profiles.ihe.net/ITI/MHD/CodeSystem/MHDlistTypes"
MHD_SOURCE_ID_EXT = "https://profiles.ihe.net/ITI/MHD/StructureDefinition/ihe-sourceId"


def provide_document_bundle(result, submitted_at: str | None = None) -> dict:
    """Build the ITI-65 transaction for one ConversionResult."""
    ctx = result.context
    document = result.document
    composition = result.composition

    patient = next(
        (r for r in ctx.resources if r["resourceType"] == "Patient"), None
    )
    if patient is None:
        # Every mapped PCR emits a Patient today, so this is a guard against a
        # future caller — but a bare next() would raise StopIteration, which
        # unwinds as a confusing generator error rather than a clear fault.
        raise ValueError(
            "cannot build an ITI-65 bundle: the conversion produced no Patient"
        )
    patient_ref = {"reference": f"urn:uuid:{patient['id']}"}
    when = submitted_at or composition.get("date")

    binary_id = ctx.rid("Binary", "iti65-document")
    docref_id = ctx.rid("DocumentReference", "iti65")
    submissionset_id = ctx.rid("List", "iti65-submissionset")

    document_json = json.dumps(document, separators=(",", ":"))

    binary = {
        "resourceType": "Binary",
        "id": binary_id,
        "contentType": "application/fhir+json",
        "data": base64.b64encode(document_json.encode()).decode(),
    }

    docref = {
        "resourceType": "DocumentReference",
        "id": docref_id,
        "meta": {"profile": [MHD_DOCUMENTREFERENCE_PROFILE]},
        "masterIdentifier": {
            "system": "urn:ietf:rfc:3986",
            "value": f"urn:uuid:{ctx.rid('Bundle', 'document')}",
        },
        "identifier": [
            # MHD EntryUUID (required shape: rfc:3986 system, urn:uuid value)
            {
                "use": "official",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{docref_id}",
            },
            # PCR business identifier rides along (slicing is open past EntryUUID)
            {"system": systems.PCR_ID, "value": ctx.pcr_number or "unknown"},
        ],
        "status": "current",
        "type": dict(composition["type"]),  # mPSC Medical Summary (LOINC 107903-7)
        "subject": patient_ref,
        **({"date": when} if when else {}),
        "content": [
            {
                "attachment": {
                    "contentType": "application/fhir+json",
                    "url": f"urn:uuid:{binary_id}",
                    **({"creation": when} if when else {}),
                }
            }
        ],
        "context": {
            "encounter": [
                {"reference": f"urn:uuid:{ctx.encounter_id}"}
            ] if ctx.encounter_id else [],
        },
    }
    if composition.get("confidentiality"):
        docref["securityLabel"] = [
            {"coding": [{"system": systems.V3_CONFIDENTIALITY, "code": composition["confidentiality"]}]}
        ]

    submissionset = {
        "resourceType": "List",
        "id": submissionset_id,
        "meta": {"profile": [MHD_SUBMISSIONSET_PROFILE]},
        "extension": [
            {
                "url": MHD_SOURCE_ID_EXT,
                "valueIdentifier": {
                    "system": systems.AGENCY_NUMBER,
                    "value": ctx.header.value("dAgency.02") or "unknown",
                },
            }
        ],
        "identifier": [
            {
                "use": "official",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{ctx.rid('List', 'iti65-uniqueid')}",
            }
        ],
        "status": "current",
        "mode": "working",
        "code": {"coding": [{"system": MHD_LIST_TYPES, "code": "submissionset"}]},
        "subject": patient_ref,
        **({"date": when} if when else {}),
        "entry": [{"item": {"reference": f"urn:uuid:{docref_id}"}}],
    }

    # The Patient travels in the bundle so subject references resolve at the
    # recipient (conditional create — MHD recipients typically match by id).
    patient_entry_resource = dict(patient)

    return {
        "resourceType": "Bundle",
        "meta": {"profile": [MHD_PROVIDE_BUNDLE_PROFILE]},
        "type": "transaction",
        **({"timestamp": when} if when else {}),
        "entry": [
            {
                "fullUrl": f"urn:uuid:{submissionset_id}",
                "resource": submissionset,
                "request": {"method": "POST", "url": "List"},
            },
            {
                "fullUrl": f"urn:uuid:{docref_id}",
                "resource": docref,
                "request": {"method": "POST", "url": "DocumentReference"},
            },
            {
                "fullUrl": f"urn:uuid:{binary_id}",
                "resource": binary,
                "request": {"method": "POST", "url": "Binary"},
            },
            {
                "fullUrl": f"urn:uuid:{patient['id']}",
                "resource": patient_entry_resource,
                "request": {"method": "POST", "url": "Patient"},
            },
        ],
    }
