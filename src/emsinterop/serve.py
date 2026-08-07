"""At-the-door push endpoint (Roadmap P6): real-time NEMSIS -> hospital rails.

A thin WSGI app over the SAME pipeline as the batch CLI — nothing is
reimplemented: XSD validation, convert(), MessagingConfig dispatch() (which
rail fires, prearrival policy, endpoints) all behave exactly as they do
offline. Point fhirEngine at `single` storage mode for read-after-write and
the pushed encounter is queryable the moment the transaction returns.

    POST /push     body: a NEMSIS EMSDataSet document (XML)
                   202-style semantics collapsed to synchronous JSON:
                   200 all configured deliveries succeeded (or none configured),
                   422 XSD-invalid (OperationOutcome body, quarantine-don't-crash),
                   502 a configured rail failed (report says which)
    GET  /healthz  liveness + the active rails

Responses carry delivery summaries only (kind/sent/error + issue counts) —
never artifacts or resource content: the response channel is not presumed
private. Raw XML is landed to bronze first when a table is configured
(hash-idempotent: EMS retries never duplicate audit rows). Deploy behind
TLS + authenticating proxy; the endpoint itself is transport-agnostic
mechanism, matching fhirEngine's TLS-terminated-at-proxy posture.

Stdlib-only (WSGI): unit tests call the app in-process; production runs any
WSGI server; `python -m emsinterop serve` uses wsgiref for dev/pilot.
"""

from __future__ import annotations

import json
from typing import Callable, Iterable

from .config import MessagingConfig, dispatch
from .convert import convert
from .ingest import to_operation_outcome, validate
from .log import event, get_logger

logger = get_logger("serve")

_JSON = [("Content-Type", "application/json")]


class PushApp:
    """WSGI application; construct via create_app()."""

    def __init__(self, config: MessagingConfig, bronze_table: str | None = None):
        self.config = config
        self.bronze_table = bronze_table

    # -- WSGI plumbing ------------------------------------------------------
    def __call__(self, environ: dict, start_response: Callable) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        if method == "GET" and path == "/healthz":
            status, body = 200, {"ok": True, "rails": list(self.config.rails)}
        elif method == "POST" and path == "/push":
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = 0
            raw = environ["wsgi.input"].read(length) if length else b""
            status, body = self.push(raw)
        else:
            status, body = 404, {"ok": False, "error": "not found"}
        payload = json.dumps(body).encode()
        start_response(f"{status} {_REASONS.get(status, '')}".strip(),
                       _JSON + [("Content-Length", str(len(payload)))])
        return [payload]

    # -- the pipeline -------------------------------------------------------
    def push(self, raw: bytes) -> tuple[int, dict]:
        if not raw:
            return 400, {"ok": False, "error": "empty body — POST a NEMSIS EMSDataSet"}

        errors = validate(raw)
        if errors:
            event(logger, "push.rejected", count=len(errors))
            return 422, to_operation_outcome(errors)

        if self.bronze_table:
            from .ingest.bronze import land
            land(raw, self.bronze_table)

        try:
            results = convert(raw, xsd_validate=False)
        except Exception:
            # XSD-valid but unconvertible would be a mapper defect; surface
            # without echoing content.
            event(logger, "push.failed", level=40)
            return 500, {"ok": False, "error": "conversion failed — see server logs"}

        pcrs, failed = [], False
        for result in results:
            try:
                report = dispatch(result, self.config)
            except Exception:
                # A transport blew up (e.g. MLLP socket refused) — the report
                # never formed; the push must still answer.
                event(logger, "push.dispatch-error", level=40,
                      pcr_number=result.context.pcr_number)
                pcrs.append({"pcr_number": result.context.pcr_number,
                             "resources": len(result.resources),
                             "issues": len(result.issues),
                             "deliveries": [{"error": "dispatch failed — see server logs"}]})
                failed = True
                continue
            entries = []
            for entry in report:
                summary = {"kind": entry["kind"], "sent": entry["sent"]}
                if "error" in entry:
                    summary["error"] = entry["error"]
                # A rail with a configured destination that did not deliver is
                # a failure; an unconfigured rail producing its artifact is not.
                if "error" in entry or (self._must_send(entry["kind"])
                                        and not entry["sent"]):
                    failed = True
                entries.append(summary)
            pcrs.append({
                "pcr_number": result.context.pcr_number,
                "resources": len(result.resources),
                "issues": len(result.issues),
                "deliveries": entries,
            })
        event(logger, "push.dispatched", count=len(pcrs))
        return (502 if failed else 200), {"ok": not failed, "pcrs": pcrs}

    def _must_send(self, kind: str) -> bool:
        config = self.config
        if kind == "fhir-transaction":
            return bool(config.fhir.fhirengine_url)
        if kind == "iti65":
            return bool(config.fhir.iti65_endpoint)
        if kind.startswith("adt-"):
            return bool(config.adt_endpoint)
        if kind == "ccda":
            return bool(config.ccda.out_dir)
        return False


_REASONS = {200: "OK", 400: "Bad Request", 404: "Not Found",
            422: "Unprocessable Entity", 500: "Internal Server Error",
            502: "Bad Gateway"}


def create_app(config: MessagingConfig | None = None,
               bronze_table: str | None = None) -> PushApp:
    return PushApp(config or MessagingConfig(), bronze_table)


def run(app: PushApp, host: str = "127.0.0.1", port: int = 8096) -> None:  # pragma: no cover
    from wsgiref.simple_server import make_server

    with make_server(host, port, app) as server:
        event(logger, "serve.listening", path=f"{host}:{port}")
        server.serve_forever()
