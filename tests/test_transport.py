"""ITI-65 Provide Document Bundle + transport adapters (ADR-008)."""

import base64
import json

import httpx

from emsinterop.transport import (
    FileDropTransport,
    MhdHttpTransport,
    provide_document_bundle,
)
from emsinterop.transport.iti65 import (
    MHD_DOCUMENTREFERENCE_PROFILE,
    MHD_SUBMISSIONSET_PROFILE,
)


def _by_type(bundle, resource_type):
    return [e for e in bundle["entry"] if e["resource"]["resourceType"] == resource_type]


def test_iti65_structure(result):
    iti65 = provide_document_bundle(result)
    assert iti65["type"] == "transaction"
    assert [e["resource"]["resourceType"] for e in iti65["entry"]] == [
        "List", "DocumentReference", "Binary", "Patient",
    ]

    submissionset = _by_type(iti65, "List")[0]["resource"]
    assert MHD_SUBMISSIONSET_PROFILE in submissionset["meta"]["profile"]
    assert submissionset["code"]["coding"][0]["code"] == "submissionset"
    assert submissionset["mode"] == "working"

    docref = _by_type(iti65, "DocumentReference")[0]["resource"]
    assert MHD_DOCUMENTREFERENCE_PROFILE in docref["meta"]["profile"]
    assert docref["type"]["coding"][0]["code"] == "107903-7"  # mirrors Composition.type
    assert docref["status"] == "current"

    # Every urn:uuid reference resolves inside the bundle.
    full_urls = {e["fullUrl"] for e in iti65["entry"]}
    assert submissionset["entry"][0]["item"]["reference"] in full_urls
    assert docref["content"][0]["attachment"]["url"] in full_urls
    assert docref["subject"]["reference"] in full_urls


def test_iti65_binary_round_trips_the_document(result):
    iti65 = provide_document_bundle(result)
    binary = _by_type(iti65, "Binary")[0]["resource"]
    decoded = json.loads(base64.b64decode(binary["data"]))
    assert decoded == result.document
    assert decoded["entry"][0]["resource"]["resourceType"] == "Composition"


def test_iti65_carries_confidentiality_as_security_label(result):
    # chest-pain has substance-use content -> Composition R -> DocRef label.
    iti65 = provide_document_bundle(result)
    docref = _by_type(iti65, "DocumentReference")[0]["resource"]
    labels = [c["code"] for sl in docref["securityLabel"] for c in sl["coding"]]
    assert "R" in labels


def test_iti65_is_deterministic(result):
    assert provide_document_bundle(result) == provide_document_bundle(result)


def test_file_drop_transport(result, tmp_path):
    iti65 = provide_document_bundle(result)
    receipt = FileDropTransport(tmp_path).send(iti65)
    assert receipt["status"] == "written"
    written = json.loads(open(receipt["path"]).read())
    assert written == iti65
    assert "PCR-2026-000123" in receipt["path"]


def test_mhd_http_transport(result):
    iti65 = provide_document_bundle(result)

    def handler(request):
        body = json.loads(request.content)
        assert body["type"] == "transaction"
        return httpx.Response(200, json={"resourceType": "Bundle", "type": "transaction-response"})

    transport = MhdHttpTransport("http://recipient.example")
    transport._client = httpx.Client(
        base_url="http://recipient.example", transport=httpx.MockTransport(handler)
    )
    receipt = transport.send(iti65)
    assert receipt["status"] == "delivered"
    assert receipt["response"]["type"] == "transaction-response"
