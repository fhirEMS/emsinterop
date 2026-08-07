"""PHI-safe mapper logging (Architecture §7, Roadmap P5).

The mapper logs METADATA ONLY: element ids, codes, dispositions, counts,
resource types, and business identifiers (PCR/agency numbers) — never
demographic values, free text, or resource content. That rule is enforced
structurally, not by convention: call sites emit through event(), which drops
any field name outside the allowlist (recording only *that* it dropped, never
the value), so a new call site cannot leak a value by accident.

Library etiquette: the "emsinterop" root logger gets a NullHandler; nothing
is written anywhere until the embedding application configures handlers.
"""

from __future__ import annotations

import logging

logging.getLogger("emsinterop").addHandler(logging.NullHandler())

# Field names event() will emit. Everything here is an identifier, a code,
# a count, or an enum — values that identify records, not people.
ALLOWED_FIELDS = frozenset({
    "pcr_number",
    "pcr_uuid",
    "agency_number",
    "element_id",
    "resource_type",
    "resource_id",
    "disposition",
    "severity",
    "code",
    "system",
    "status_code",
    "kind",
    "sent",
    "count",
    "resources",
    "issues",
    "entries",
    "rows",
    "table",
    "path",
    "nemsis_version",
    "variant",
    "event_type",
    "verdict",
})


def get_logger(name: str) -> logging.Logger:
    """Namespaced mapper logger: get_logger("submit") → "emsinterop.submit"."""
    return logging.getLogger(f"emsinterop.{name}")


def event(
    logger: logging.Logger,
    name: str,
    level: int = logging.INFO,
    **fields: object,
) -> None:
    """Emit a structured event line: "name key=value key=value".

    Non-allowlisted fields are dropped; only their NAMES are recorded (in
    dropped_fields), never their values.
    """
    if not logger.isEnabledFor(level):
        return
    dropped = sorted(set(fields) - ALLOWED_FIELDS)
    safe = {k: v for k, v in sorted(fields.items()) if k in ALLOWED_FIELDS}
    if dropped:
        safe["dropped_fields"] = ",".join(dropped)
    rendered = " ".join(f"{k}={v}" for k, v in safe.items())
    logger.log(level, "%s %s", name, rendered)
