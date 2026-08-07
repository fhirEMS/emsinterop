"""fhirEngine client over a mock transport (no live server needed)."""

import httpx
import pytest

from emsinterop.submit import FhirEngineClient, SubmissionError


def _client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url="http://fhirengine.local", transport=transport)
    return FhirEngineClient(base_url="http://fhirengine.local", client=http)


def test_submit_success(result):
    def handler(request):
        assert request.url.path == "/"
        return httpx.Response(200, json={"resourceType": "Bundle", "type": "transaction-response"})

    response = _client(handler).submit(result.transaction)
    assert response["type"] == "transaction-response"


def test_submit_failure_carries_operation_outcome(result):
    outcome = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "error", "code": "invalid"}],
    }

    def handler(request):
        return httpx.Response(422, json=outcome)

    with pytest.raises(SubmissionError) as excinfo:
        _client(handler).submit(result.transaction)
    assert excinfo.value.status_code == 422
    assert excinfo.value.operation_outcome == outcome
