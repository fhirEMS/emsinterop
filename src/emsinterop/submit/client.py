"""fhirEngine REST client — the only path by which FHIR data is persisted.

Hard rule (ADR-009): never write FHIR resources to Delta directly; fhirEngine
owns validation-prior-to-Bronze, indexing, persistence, MPI, and security.
"""

from __future__ import annotations

import httpx


class SubmissionError(RuntimeError):
    def __init__(self, status_code: int, operation_outcome: dict | None):
        self.status_code = status_code
        self.operation_outcome = operation_outcome
        super().__init__(f"fhirEngine transaction failed with HTTP {status_code}")


class FhirEngineClient:
    """Thin client for fhirEngine's FHIR R4 REST API."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        # Large transactions (60-90 conditional upserts through serialized
        # Delta MERGEs) legitimately take minutes as version history grows.
        timeout: float = 300.0,
        client: httpx.Client | None = None,
    ):
        headers = {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(
            base_url=base_url, headers=headers, timeout=timeout
        )

    def submit(self, bundle: dict) -> dict:
        """POST a transaction Bundle to the server root."""
        response = self._client.post("/", json=bundle)
        if response.status_code >= 300:
            outcome = None
            try:
                body = response.json()
                if body.get("resourceType") == "OperationOutcome":
                    outcome = body
            except ValueError:
                pass
            raise SubmissionError(response.status_code, outcome)
        return response.json()

    def capability(self) -> dict:
        response = self._client.get("/metadata")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()
