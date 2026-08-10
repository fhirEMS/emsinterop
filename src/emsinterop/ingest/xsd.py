"""XSD validation against the pinned NEMSIS 3.5.0 schemas (Architecture §5.2).

Structural violations hard-fail to quarantine with a machine-readable
OperationOutcome; Schematron/business rules (warn-only) come later.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lxml import etree

from . import safexml

SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas" / "nemsis"
PINNED_VERSION = "3.5.0"

#: NEMSIS releases whose schemas are vendored here. 3.5.1's XSDs differ from
#: 3.5.0's by exactly ONE line — ePatient.25 gains an explicit minOccurs="1",
#: which is XSD's default and therefore a no-op clarification. Verified by
#: normalizing line endings and diffing all 46 files; the whole golden and
#: hostile corpora validate identically against both. So a 3.5.1 document is
#: structurally a 3.5.0 document, and vice versa — but we validate against the
#: version the document DECLARES rather than assuming that stays true.
SUPPORTED_VERSIONS = ("3.5.0", "3.5.1")

#: Root XSD file per NEMSIS dataset kind (both pinned in schemas/nemsis/<version>/).
DATASET_XSDS = {
    "EMSDataSet": "EMSDataSet_v3.xsd",
    "DEMDataSet": "DEMDataSet_v3.xsd",
}


@lru_cache(maxsize=4)
def _schema(version: str = PINNED_VERSION, dataset: str = "EMSDataSet") -> etree.XMLSchema:
    try:
        root_xsd = DATASET_XSDS[dataset]
    except KeyError:
        raise ValueError(f"Unknown NEMSIS dataset kind: {dataset!r} (expected one of {sorted(DATASET_XSDS)})")
    xsd_path = SCHEMA_ROOT / version / root_xsd
    if not xsd_path.exists():
        raise FileNotFoundError(f"No pinned NEMSIS schema for version {version}: {xsd_path}")
    return etree.XMLSchema(etree.parse(str(xsd_path)))


def validate_dataset(
    source: str | Path | bytes,
    dataset: str = "EMSDataSet",
    version: str = PINNED_VERSION,
) -> list[str]:
    """Validate any pinned NEMSIS dataset kind; returns error strings (empty = valid)."""
    try:
        if isinstance(source, bytes):
            doc = safexml.fromstring(source).getroottree()
        else:
            doc = safexml.parse(source)
    except (etree.XMLSyntaxError, ValueError, UnicodeDecodeError) as error:
        # Quarantine, don't crash (Architecture §8). This is the boundary that
        # owns that rule, so fixing it here also fixes the push endpoint, the
        # CLI, and convert(). The message names the fault, never the content —
        # an untrusted body must not be echoed into logs or responses.
        return [f"line 0: not well-formed XML: {type(error).__name__}"]
    schema = _schema(version, dataset)
    if schema.validate(doc):
        return []
    return [f"line {e.line}: {e.message}" for e in schema.error_log]


def resolve_version(declared: str | None) -> str:
    """Which vendored schema set validates a document declaring `declared`?

    Unknown or absent -> the pinned default. We do NOT guess forward: a future
    3.5.2 validates against 3.5.0's schemas and any genuine difference surfaces
    as a validation error rather than being silently accepted."""
    if declared in SUPPORTED_VERSIONS:
        return declared
    return PINNED_VERSION


def validate(
    source: str | Path | bytes, version: str | None = None
) -> list[str]:
    """Validate an EMSDataSet document; returns error strings (empty = valid).

    With no explicit version, validates against the release the document
    itself declares (`xsi:schemaLocation`), falling back to the pinned one."""
    if version is None:
        version = resolve_version(_declared_version(source))
    return validate_dataset(source, "EMSDataSet", version)


def _declared_version(source: str | Path | bytes) -> str | None:
    """The NEMSIS release a document declares, without a full parse."""
    from .parser import declared_version

    try:
        return declared_version(source)
    except Exception:
        return None


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
