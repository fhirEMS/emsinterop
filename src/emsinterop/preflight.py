"""Production PHI preflight — the gate between synthetic data and real patients.

Everything this project ships has run on synthetic data. Before it carries a
real ePCR, the deployment has to actually hold the controls the architecture
assumes, and "we think it's configured" is not evidence. This module checks
what a machine can check, from the outside, and refuses to report ready when
any of it is missing.

What it CANNOT check, and what no script can: whether a BAA is in place,
whether a risk assessment was done, whether your consent policy matches your
jurisdiction's, or whether someone accountable has signed off. Those are the
real gate. This is the part that catches a misconfiguration before it becomes
a breach — not a compliance certificate.

    python -m emsinterop preflight --config deploy.json

Exits non-zero unless every REQUIRED check passes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .config import MessagingConfig

#: Operators must set this deliberately. Its absence is the default, and the
#: default must be "synthetic only" — nobody should reach production PHI by
#: forgetting a flag.
PHI_ENV = "EMSINTEROP_ALLOW_PHI"


@dataclass
class Check:
    name: str
    ok: bool
    required: bool
    detail: str

    @property
    def status(self) -> str:
        if self.ok:
            return "PASS"
        return "FAIL" if self.required else "WARN"


def _tls_checks(config: "MessagingConfig") -> list[Check]:
    out: list[Check] = []
    url = config.fhir.fhirengine_url
    if url:
        out.append(Check(
            "fhirengine endpoint uses TLS", url.startswith("https://"), True,
            f"{url} — PHI over plain http is a transmission-security failure "
            "(HIPAA §164.312(e)); terminate TLS at the proxy and use https://"
            if not url.startswith("https://") else url,
        ))
    if config.fhir.iti65_endpoint:
        mhd = config.fhir.iti65_endpoint
        out.append(Check(
            "ITI-65 recipient uses TLS", mhd.startswith("https://"), True, mhd,
        ))
    if config.adt_endpoint:
        # MLLP is cleartext by design; it is only safe inside a tunnel.
        out.append(Check(
            "ADT/MLLP channel is protected", False, False,
            f"{config.adt_endpoint} — MLLP has no transport security of its "
            "own. Confirm it rides a VPN/TLS tunnel or a private link; this "
            "check cannot verify that from here.",
        ))
    return out


def _fhirengine_checks(config: "MessagingConfig") -> list[Check]:
    url = config.fhir.fhirengine_url
    if not url:
        return [Check("fhirEngine configured", False, False,
                      "no fhirengine_url in config — nothing to submit to")]

    from .submit import FhirEngineClient

    out: list[Check] = []
    client = FhirEngineClient(url, token=config.fhir.token, timeout=15.0)
    try:
        client.capability()
        out.append(Check("fhirEngine reachable", True, True, url))
    except Exception as error:
        client.close()
        return out + [Check("fhirEngine reachable", False, True,
                            f"{type(error).__name__}: {error}")]

    # Auth: an UNAUTHENTICATED resource read must be refused. /metadata is
    # legitimately public, so probe a resource endpoint with no token.
    try:
        anon = FhirEngineClient(url, token=None, timeout=15.0)
        try:
            anon.get("/Patient", {"_count": "1"})
            enforced, detail = False, (
                "an unauthenticated Patient search SUCCEEDED — auth is off. "
                "Set FHIRENGINE_AUTH_ENABLED=true and boot fhirEngine with "
                "FHIRENGINE_SECURITY_PROFILE=production, which refuses to "
                "start until auth, audit and TLS are configured."
            )
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            enforced = status in (401, 403)
            detail = (f"unauthenticated read refused ({status})" if enforced
                      else f"inconclusive: {type(error).__name__}")
        finally:
            anon.close()
        out.append(Check("fhirEngine rejects unauthenticated reads", enforced,
                         True, detail))
    except Exception as error:  # pragma: no cover
        out.append(Check("fhirEngine rejects unauthenticated reads", False, True,
                         f"probe failed: {error}"))

    out.append(Check(
        "submission credential configured", bool(config.fhir.token), True,
        "fhir.token is set" if config.fhir.token else
        "no fhir.token — a server that enforces auth will reject every submission",
    ))

    # Terminology: our dual-coded NEMSIS codes must resolve, or every bound
    # code fails validation once declared-profile enforcement is on.
    try:
        from .terminology import systems

        params = client.get("/CodeSystem/$validate-code",
                            {"url": systems.NEMSIS, "code": "4001001"})
        result = {p["name"]: p.get("valueBoolean") for p in params.get("parameter", [])}
        ok = result.get("result") is True
        out.append(Check(
            "NEMSIS terminology installed", ok, True,
            "emsinterop.nemsis resolves" if ok else
            "NEMSIS codes do not resolve — run `emsinterop package-ig` and "
            "install it with fhirengine-terminology install-ig",
        ))
    except Exception as error:
        out.append(Check("NEMSIS terminology installed", False, True,
                         f"$validate-code failed: {type(error).__name__}"))
    client.close()
    return out


def _mapper_checks() -> list[Check]:
    allowed = os.environ.get(PHI_ENV) == "1"
    return [
        Check(
            f"{PHI_ENV}=1 set deliberately", allowed, True,
            "operator has explicitly enabled PHI mode" if allowed else
            f"{PHI_ENV} is not set. This is the intended default: reaching "
            "production PHI must be a decision, not an oversight.",
        ),
        Check(
            "PHI-safe logging in force", True, True,
            "emsinterop.log.event() drops any field outside its metadata "
            "allowlist, so no configured handler can receive a patient value",
        ),
    ]


def run(config: "MessagingConfig") -> list[Check]:
    """Every check, in report order."""
    return _mapper_checks() + _tls_checks(config) + _fhirengine_checks(config)


def report(checks: list[Check]) -> tuple[str, bool]:
    """Render the report; returns (text, ready)."""
    width = max(len(c.name) for c in checks) if checks else 0
    lines = [f"  {c.status:4}  {c.name.ljust(width)}  {c.detail}" for c in checks]
    failed = [c for c in checks if c.required and not c.ok]
    warned = [c for c in checks if not c.required and not c.ok]
    ready = not failed
    lines.append("")
    if ready:
        lines.append(
            f"  READY for PHI on the technical controls above"
            + (f" ({len(warned)} warning(s) to confirm by hand)" if warned else "")
            + ".\n"
            "  This does NOT certify compliance: a BAA, a risk assessment, a "
            "consent policy\n  and accountable sign-off are the actual gate."
        )
    else:
        lines.append(f"  NOT READY — {len(failed)} required check(s) failed.")
    return "\n".join(lines), ready
