"""Deployment messaging configuration: which rails a converted call rides.

One switch picks the modality — `fhir` (transaction to fhirEngine + optional
ITI-65 handoff; the default), `adt` (HL7 v2 per AdtConfig), or `both` — with
per-rail policy nested underneath. Loadable from a JSON file so a deployment
is one --config away:

    {
      "mode": "adt",
      "adt": {"send_prearrival": true, "receiving_facility": "STATE-HIE",
              "endpoint": "hie.example.org:2575"},
      "fhir": {"fhirengine_url": "http://localhost:8080", "iti65": true}
    }

dispatch() is mechanism, not policy: it produces the configured artifacts and
sends only where an endpoint is configured, returning a delivery report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .assemble.adt import AdtConfig, build_adt_messages

MODES = ("fhir", "adt", "both")


@dataclass
class FhirConfig:
    fhirengine_url: str | None = None  # submit the transaction when set
    token: str | None = None
    iti65: bool = False  # also produce the ITI-65 Provide Document Bundle
    iti65_endpoint: str | None = None  # MHD recipient base URL; send when set


@dataclass
class MessagingConfig:
    mode: str = "fhir"
    fhir: FhirConfig = field(default_factory=FhirConfig)
    adt: AdtConfig = field(default_factory=AdtConfig)
    adt_endpoint: str | None = None  # "host:port" MLLP; send when set

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}")

    @property
    def wants_fhir(self) -> bool:
        return self.mode in ("fhir", "both")

    @property
    def wants_adt(self) -> bool:
        return self.mode in ("adt", "both")

    @classmethod
    def from_dict(cls, data: dict) -> "MessagingConfig":
        return cls(
            mode=data.get("mode", "fhir"),
            fhir=FhirConfig(**data.get("fhir", {})),
            adt=AdtConfig(**data.get("adt", {})),
            adt_endpoint=data.get("adt_endpoint"),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "MessagingConfig":
        return cls.from_dict(json.loads(Path(path).read_text()))


def dispatch(result, config: MessagingConfig | None = None) -> list[dict]:
    """Produce (and, where endpoints are configured, deliver) the configured
    outputs for one ConversionResult. Returns one report entry per artifact:
    {"kind", "sent", "detail"/"artifact"}."""
    config = config or MessagingConfig()
    report: list[dict] = []

    if config.wants_fhir:
        entry: dict = {"kind": "fhir-transaction", "sent": False,
                       "artifact": result.transaction}
        if config.fhir.fhirengine_url:
            from .submit import FhirEngineClient
            client = FhirEngineClient(config.fhir.fhirengine_url, token=config.fhir.token)
            entry["detail"] = client.submit(result.transaction)
            entry["sent"] = True
        report.append(entry)
        if config.fhir.iti65:
            from .transport import MhdHttpTransport, provide_document_bundle
            bundle = provide_document_bundle(result)
            entry = {"kind": "iti65", "sent": False, "artifact": bundle}
            if config.fhir.iti65_endpoint:
                entry["detail"] = MhdHttpTransport(config.fhir.iti65_endpoint).send(bundle)
                entry["sent"] = True
            report.append(entry)

    if config.wants_adt:
        transport = None
        if config.adt_endpoint:
            from .transport import MllpTransport
            host, _, port = config.adt_endpoint.rpartition(":")
            transport = MllpTransport(host, int(port))
        for event, message in build_adt_messages(result.context, config.adt):
            entry = {"kind": f"adt-{event.lower()}", "sent": False, "artifact": message}
            if transport is not None:
                entry["detail"] = transport.send(message)
                entry["sent"] = entry["detail"].get("status") == "delivered"
            report.append(entry)

    return report
