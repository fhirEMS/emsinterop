"""At-the-door push endpoint: the WSGI app exercised in-process — same
pipeline as the batch CLI, synchronous delivery report, artifacts never
echoed back."""

import io
import json

import pytest

from emsinterop.config import MessagingConfig
from emsinterop.serve import create_app

from .conftest import CHEST_PAIN


def call(app, method="GET", path="/", body=b""):
    captured = {}

    def start_response(status, headers):
        captured["status"] = int(status.split()[0])
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    payload = b"".join(app(environ, start_response))
    return captured["status"], json.loads(payload)


def test_healthz_reports_rails():
    app = create_app(MessagingConfig(mode=["fhir", "adt"]))
    status, body = call(app, "GET", "/healthz")
    assert status == 200
    assert body == {"ok": True, "rails": ["fhir", "adt"]}


def test_push_produces_artifacts_without_endpoints():
    """No endpoints configured -> artifacts are produced and reported, the
    push succeeds, and nothing counts as a failed delivery."""
    app = create_app(MessagingConfig(mode=["fhir", "adt"]))
    status, body = call(app, "POST", "/push", CHEST_PAIN.read_bytes())
    assert status == 200 and body["ok"] is True

    (pcr,) = body["pcrs"]
    assert pcr["pcr_number"] == "PCR-2026-000123"
    assert pcr["resources"] > 50
    kinds = {d["kind"] for d in pcr["deliveries"]}
    assert "fhir-transaction" in kinds and any(k.startswith("adt-") for k in kinds)
    assert all(d["sent"] is False for d in pcr["deliveries"])
    # Delivery summaries only — never resource content.
    assert "artifact" not in json.dumps(body) and "Trujillo" not in json.dumps(body)


def test_push_rejects_invalid_xml_with_operation_outcome():
    app = create_app(MessagingConfig())
    mutated = CHEST_PAIN.read_text().replace("<eScene.01>", "<eScene.99><eScene.01>", 1) \
                                    .replace("</eScene.01>", "</eScene.01></eScene.99>", 1)
    status, body = call(app, "POST", "/push", mutated.encode())
    assert status == 422
    assert body["resourceType"] == "OperationOutcome"
    assert body["issue"]


def test_push_empty_body_is_400():
    status, body = call(create_app(), "POST", "/push", b"")
    assert status == 400 and body["ok"] is False


def test_unknown_route_is_404():
    status, body = call(create_app(), "GET", "/nope")
    assert status == 404


def test_push_lands_bronze_idempotently(tmp_path):
    deltalake = pytest.importorskip("deltalake")
    table = tmp_path / "bronze"
    app = create_app(MessagingConfig(mode="adt"), bronze_table=str(table))
    raw = CHEST_PAIN.read_bytes()
    assert call(app, "POST", "/push", raw)[0] == 200
    assert call(app, "POST", "/push", raw)[0] == 200  # EMS retry
    rows = deltalake.DeltaTable(str(table)).to_pyarrow_table()
    assert rows.num_rows == 1  # hash-idempotent: retries never duplicate audit


def test_push_reports_502_when_configured_rail_fails(monkeypatch):
    import emsinterop.submit as submit

    class RejectingClient:
        def __init__(self, *args, **kwargs):
            pass

        def submit(self, bundle):
            raise submit.SubmissionError(422, {"resourceType": "OperationOutcome",
                                               "issue": []})

    monkeypatch.setattr(submit, "FhirEngineClient", RejectingClient)
    app = create_app(MessagingConfig.from_dict(
        {"mode": "fhir", "fhir": {"fhirengine_url": "http://unreachable"}}))
    status, body = call(app, "POST", "/push", CHEST_PAIN.read_bytes())
    assert status == 502 and body["ok"] is False
    delivery = body["pcrs"][0]["deliveries"][0]
    assert delivery["sent"] is False and delivery["error"] == "HTTP 422"


def test_push_survives_transport_crash(monkeypatch):
    """A raising transport (MLLP socket refused) must yield a 502 report,
    not a WSGI traceback."""
    import emsinterop.config as config_module

    def exploding_dispatch(result, config=None):
        raise OSError("connection refused")

    monkeypatch.setattr(config_module, "dispatch", exploding_dispatch)
    monkeypatch.setattr("emsinterop.serve.dispatch", exploding_dispatch)
    app = create_app(MessagingConfig(mode="adt"))
    status, body = call(app, "POST", "/push", CHEST_PAIN.read_bytes())
    assert status == 502 and body["ok"] is False
    assert "error" in body["pcrs"][0]["deliveries"][0]
