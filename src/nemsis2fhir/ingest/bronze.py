"""Raw-NEMSIS bronze: the mapper's ONE Delta table (source audit/replay).

This is the only Delta table the mapper owns (ADR-009). It stores raw source
XML + metadata, one row per PatientCareReport — it never holds FHIR resources
(fhirEngine is the sole writer of FHIR storage).

Requires the optional `bronze` extra (deltalake); imported lazily so the core
mapper has no heavy dependencies.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

from .parser import NEMSIS_NS, parse


def land(xml_path: str | Path, table_path: str | Path) -> int:
    """Shred an EMSDataSet file into the bronze table; returns rows written."""
    try:
        import pyarrow as pa
        from deltalake import write_deltalake
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(
            "raw-NEMSIS bronze requires the 'bronze' extra: pip install nemsis2fhir[bronze]"
        ) from error

    raw = Path(xml_path).read_bytes()
    dataset = parse(raw)
    file_hash = hashlib.sha256(raw).hexdigest()
    received_at = datetime.now(timezone.utc).isoformat()
    agency = dataset.header.value("dAgency.02")

    # Re-serialize each PatientCareReport for row-level replay.
    root = etree.fromstring(raw)
    pcr_nodes = root.findall(f".//{{{NEMSIS_NS}}}PatientCareReport")

    rows = {
        "pcr_number": [],
        "pcr_uuid": [],
        "agency_number": [],
        "nemsis_version": [],
        "file_sha256": [],
        "received_at": [],
        "raw_xml": [],
    }
    for pcr, node in zip(dataset.reports, pcr_nodes):
        record = pcr.section("eRecord")
        rows["pcr_number"].append(pcr.pcr_number)
        rows["pcr_uuid"].append(record.uuid if record else None)
        rows["agency_number"].append(agency)
        rows["nemsis_version"].append(dataset.nemsis_version)
        rows["file_sha256"].append(file_hash)
        rows["received_at"].append(received_at)
        rows["raw_xml"].append(etree.tostring(node, encoding="unicode"))

    write_deltalake(str(table_path), pa.table(rows), mode="append")
    return len(dataset.reports)
