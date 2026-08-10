"""The production PHI preflight — the gate between synthetic data and real
patients. These pin the refusals, because a preflight that passes when it
shouldn't is worse than no preflight."""

import pytest

from emsinterop.config import MessagingConfig
from emsinterop.preflight import PHI_ENV, report, run


def _names(checks):
    return {c.name: c for c in checks}


def test_refuses_without_explicit_opt_in(monkeypatch):
    """Reaching production PHI must be a decision, never an oversight."""
    monkeypatch.delenv(PHI_ENV, raising=False)
    checks = run(MessagingConfig())
    opt_in = _names(checks)[f"{PHI_ENV}=1 set deliberately"]
    assert opt_in.ok is False and opt_in.required
    _, ready = report(checks)
    assert ready is False


def test_refuses_plaintext_endpoints(monkeypatch):
    monkeypatch.setenv(PHI_ENV, "1")
    config = MessagingConfig.from_dict(
        {"mode": "fhir", "fhir": {"fhirengine_url": "http://fhir.example.org"}})
    tls = _names(run(config))["fhirengine endpoint uses TLS"]
    assert tls.ok is False and tls.required
    assert "164.312(e)" in tls.detail


def test_mllp_is_warned_not_silently_accepted(monkeypatch):
    """MLLP has no transport security of its own; we cannot verify the tunnel
    from here, so it must surface as something a human confirms."""
    monkeypatch.setenv(PHI_ENV, "1")
    config = MessagingConfig(mode="adt", adt_endpoint="hie.example.org:2575")
    mllp = _names(run(config))["ADT/MLLP channel is protected"]
    assert mllp.ok is False and mllp.required is False
    assert mllp.status == "WARN"


def test_report_never_claims_compliance(monkeypatch):
    """A green preflight is a configuration check, not a certificate — the
    wording must not let anyone mistake it for one."""
    monkeypatch.setenv(PHI_ENV, "1")
    text, ready = report(run(MessagingConfig()))
    assert ready is True  # no endpoints configured, nothing to fail
    assert "does NOT certify compliance" in text
    assert "BAA" in text and "sign-off" in text
