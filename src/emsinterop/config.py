"""Deployment messaging configuration: which rails a converted call rides.

One switch picks the modality — `fhir` (transaction to fhirEngine + optional
ITI-65 handoff; the default), `adt` (HL7 v2 per AdtConfig), `ccda` (C-CDA CCD
via the optional nemsis2ccda package), or a list of rails — with per-rail
policy nested underneath. Loadable from a JSON file so a deployment
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

RAILS = ("fhir", "adt", "ccda")
_LEGACY_MODES = {"both": ("fhir", "adt"), "all": RAILS}


@dataclass
class CcdaConfig:
    """C-CDA rail (rendered by the optional nemsis2ccda package)."""

    out_dir: str | None = None  # write .ccda.xml files when set


@dataclass
class FhirConfig:
    fhirengine_url: str | None = None  # submit the transaction when set
    token: str | None = None
    iti65: bool = False  # also produce the ITI-65 Provide Document Bundle
    iti65_endpoint: str | None = None  # MHD recipient base URL; send when set


@dataclass
class MessagingConfig:
    """`mode` accepts a single rail ("fhir" | "adt" | "ccda"), a list of
    rails, or the legacy shorthands "both" (fhir+adt) / "all"."""

    mode: str | list[str] = "fhir"
    fhir: FhirConfig = field(default_factory=FhirConfig)
    adt: AdtConfig = field(default_factory=AdtConfig)
    ccda: CcdaConfig = field(default_factory=CcdaConfig)
    adt_endpoint: str | None = None  # "host:port" MLLP; send when set

    def __post_init__(self) -> None:
        raw = self.mode
        if isinstance(raw, str):
            rails = _LEGACY_MODES.get(raw, (raw,))
        else:
            rails = tuple(raw)
        bad = [r for r in rails if r not in RAILS]
        if bad or not rails:
            raise ValueError(f"mode rails must be from {RAILS}, got {raw!r}")
        self.rails: tuple[str, ...] = rails

    @property
    def wants_fhir(self) -> bool:
        return "fhir" in self.rails

    @property
    def wants_adt(self) -> bool:
        return "adt" in self.rails

    @property
    def wants_ccda(self) -> bool:
        return "ccda" in self.rails

    @classmethod
    def from_dict(cls, data: dict) -> "MessagingConfig":
        return cls(
            mode=data.get("mode", "fhir"),
            fhir=FhirConfig(**data.get("fhir", {})),
            adt=AdtConfig(**data.get("adt", {})),
            ccda=CcdaConfig(**data.get("ccda", {})),
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

    if config.wants_ccda:
        entry = {"kind": "ccda", "sent": False}
        try:
            from nemsis2ccda import render_ccda
        except ImportError:
            entry["error"] = ("ccda rail requires the nemsis2ccda package: "
                              "pip install nemsis2ccda (or -e a sibling checkout)")
        else:
            xml = render_ccda(result.context)
            entry["artifact"] = xml.decode("utf-8")
            if config.ccda.out_dir:
                out = Path(config.ccda.out_dir)
                out.mkdir(parents=True, exist_ok=True)
                target = out / f"{result.context.pcr_number or 'pcr'}.ccda.xml"
                target.write_bytes(xml)
                entry["detail"] = {"status": "written", "path": str(target)}
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
