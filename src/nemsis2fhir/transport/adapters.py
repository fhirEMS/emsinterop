"""Transport adapters (ADR-008): the binding is deliberately loose, so where a
document goes — direct MHD push, HIE publish, portable media, file drop — is a
config choice behind one interface. ITI-65 over HTTP is the default; the file
drop stands in for XDM-style portable media (true XDR/XDM SOAP bindings can
join later behind the same Protocol).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import httpx


class Transport(Protocol):
    def send(self, iti65_bundle: dict) -> dict:
        """Deliver a Provide Document Bundle; returns a delivery receipt."""
        ...


class MhdHttpTransport:
    """POST the ITI-65 transaction to a Document Recipient's FHIR base."""

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 120.0):
        headers = {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout)

    def send(self, iti65_bundle: dict) -> dict:
        response = self._client.post("/", json=iti65_bundle)
        response.raise_for_status()
        return {"status": "delivered", "http_status": response.status_code,
                "response": response.json() if response.content else None}

    def close(self) -> None:
        self._client.close()


class FileDropTransport:
    """Write the ITI-65 bundle to a directory (portable-media / batch handoff)."""

    def __init__(self, directory: str | Path):
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def send(self, iti65_bundle: dict) -> dict:
        identifier = next(
            (i["value"]
             for e in iti65_bundle.get("entry", [])
             if e["resource"]["resourceType"] == "DocumentReference"
             for i in e["resource"].get("identifier", [])
             if i.get("system") == "urn:nemsis:identifier:pcr"),
            "document",
        )
        safe = identifier.replace(":", "_").replace("/", "_")
        path = self._directory / f"iti65-{safe}.json"
        path.write_text(json.dumps(iti65_bundle, indent=1))
        return {"status": "written", "path": str(path)}


class MllpTransport:
    """Deliver HL7 v2 messages (e.g. ADT^A03/A04) over MLLP.

    Minimal Lower Layer Protocol: <VT>message<FS><CR>, one ACK read back.
    The receipt reports the MSA acknowledgment code (AA/AE/AR)."""

    VT, FS, CR = b"\x0b", b"\x1c", b"\x0d"

    def __init__(self, host: str, port: int, timeout: float = 30.0):
        self._host = host
        self._port = port
        self._timeout = timeout

    def send(self, message: str) -> dict:
        import socket

        with socket.create_connection((self._host, self._port), timeout=self._timeout) as sock:
            sock.sendall(self.VT + message.encode("utf-8") + self.FS + self.CR)
            buffer = b""
            while self.FS not in buffer:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk
        ack = buffer.strip(self.VT + self.FS + self.CR).decode("utf-8", "replace")
        code = next(
            (seg.split("|")[1] for seg in ack.split("\r") if seg.startswith("MSA")),
            None,
        )
        return {"status": "delivered" if code == "AA" else "ack-error",
                "ack_code": code, "ack": ack}
