"""XSD validation against the pinned NEMSIS 3.5.0 schemas (Architecture §5.2).

Structural violations hard-fail to quarantine with a machine-readable
OperationOutcome; Schematron/business rules (warn-only) come later.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lxml import etree

SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas" / "nemsis"
PINNED_VERSION = "3.5.0"


@lru_cache(maxsize=4)
def _schema(version: str = PINNED_VERSION) -> etree.XMLSchema:
    xsd_path = SCHEMA_ROOT / version / "EMSDataSet_v3.xsd"
    if not xsd_path.exists():
        raise FileNotFoundError(f"No pinned NEMSIS schema for version {version}: {xsd_path}")
    return etree.XMLSchema(etree.parse(str(xsd_path)))


def validate(source: str | Path | bytes, version: str = PINNED_VERSION) -> list[str]:
    """Validate a document; returns a list of error strings (empty = valid)."""
    if isinstance(source, bytes):
        doc = etree.fromstring(source).getroottree()
    else:
        doc = etree.parse(str(source))
    schema = _schema(version)
    if schema.validate(doc):
        return []
    return [f"line {e.line}: {e.message}" for e in schema.error_log]


def to_operation_outcome(errors: list[str]) -> dict:
    """Machine-readable quarantine record for an XSD-invalid document."""
    return {
        "resourceType": "OperationOutcome",
        "issue": [
            {
                "severity": "error",
                "code": "structure",
                "diagnostics": message,
            }
            for message in errors
        ]
        or [{"severity": "information", "code": "informational", "diagnostics": "valid"}],
    }
